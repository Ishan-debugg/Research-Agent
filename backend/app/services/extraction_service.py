"""
Stage 4: Structured extraction via Gemini (extraction tier model).

Key improvements over the original:
  1. FEW-SHOT PROMPTING — 2 high-quality examples are injected into the prompt
     before the actual papers, dramatically improving JSON schema adherence and
     reducing hallucinated metric values.

  2. SQLITE CACHE — Each paper's extraction is cached by arxiv_id. On a cache
     hit, the Gemini call is skipped entirely (0 tokens consumed).

  3. ASYNC + SEMAPHORE CONCURRENCY — extract_papers() is now async and accepts
     an asyncio.Semaphore so the caller (main.py) can cap simultaneous Gemini
     calls to GEMINI_CONCURRENCY (default: 3).

  4. DETERMINISTIC TEMPERATURE — extraction runs at temperature=0.0 via
     gemini_client, eliminating hallucinated numeric values.

  5. FULL TEXT — The brittle text[1500:10000] slice is removed. The full
     extracted PDF text is sent; Gemini 2.5 models handle large contexts well,
     and the cache prevents re-paying that token cost on repeated lookups.

Few-shot structure (modular — add/remove examples by editing FEW_SHOT_EXAMPLES):
  EXTRACTION_PROMPT_TEMPLATE
    └── {examples}  ← rendered from FEW_SHOT_EXAMPLES list
    └── {papers_block} ← actual papers to process
"""

import asyncio
import json
import logging
import os

import google.generativeai as genai
from dotenv import load_dotenv

from app.models.schemas import ExtractedPaper
from app.services import cache_service
from app.services import gemini_client

load_dotenv()
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# Keep MODEL_NAME exported for backward-compat (techmatch_service imports it)
MODEL_NAME = gemini_client.MODEL_NAME

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Few-shot examples — each is (input_excerpt, output_json_string)
# Add or remove examples here; extraction logic is unaffected.
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    (
        # ---- Example 1: NLP / RAG paper ----
        """arxiv_id: 2005.11401
title: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks
text:
We combine a pre-trained seq2seq model (BART-large) with a dense retrieval
component (DPR) over a Wikipedia index of 21M passages. The retriever fetches
the top-k passages for a given input; the generator conditions on them to produce
the answer. We evaluate on Natural Questions (NQ), TriviaQA, WebQuestions, and
CuratedTrec, reporting exact-match scores. On NQ our RAG model achieves 44.5 EM,
outperforming the T5-11B baseline (34.5 EM) by 10 points without any fine-tuning
on the downstream task. F1 on NQ is 57.7. The main limitation is that retrieval
quality degrades for highly specialised domains not well covered by Wikipedia.""",
        """{
  "arxiv_id": "2005.11401",
  "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
  "problem": "Open-domain QA systems struggle with knowledge-intensive tasks because parametric LLMs cannot be easily updated with new facts.",
  "method": "A seq2seq generator (BART-large) is augmented with a dense retriever (DPR) that fetches top-k Wikipedia passages at inference time, conditioning generation on retrieved context.",
  "dataset": "Natural Questions (~79k QA pairs), TriviaQA (~95k), WebQuestions (~5.8k), CuratedTrec (~2k)",
  "eval_method": "zero-shot",
  "results": "RAG achieves 44.5 EM on Natural Questions, a 10-point gain over the T5-11B baseline (34.5 EM); F1 reaches 57.7 on NQ.",
  "contribution": "Introduces a differentiable retrieval-augmented generation framework that outperforms large parametric-only models on open-domain QA without task-specific fine-tuning.",
  "limitations": "Retrieval quality degrades for highly specialised domains not well covered by Wikipedia.",
  "prerequisites": "Familiarity with seq2seq models (BART), dense passage retrieval (DPR), and open-domain QA benchmarks.",
  "real_world_impact": "Enables practical, updatable QA systems that do not require expensive full model retraining when new knowledge is introduced.",
  "audience": "NLP researchers building open-domain QA or knowledge-intensive generation systems",
  "precision": "Not reported",
  "recall": "Not reported",
  "f1_score": "57.7 (NQ)",
  "accuracy": "Not reported",
  "auc": "Not reported",
  "bleu": "Not reported",
  "rouge": "Not reported",
  "other_metrics": "Exact Match: 44.5 (NQ)",
  "baseline": "T5-11B (34.5 EM on NQ)"
}"""
    ),
    (
        # ---- Example 2: Computer Vision / classification paper ----
        """arxiv_id: 2010.11929
title: An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale
text:
We split each image into fixed-size 16×16 patches and feed linear embeddings of
those patches as tokens to a standard Transformer encoder. Pre-training on
JFT-300M (300M images, 18k classes) and fine-tuning on ImageNet-1k, our
Vision Transformer (ViT-L/16) achieves 88.55% top-1 accuracy on ImageNet,
surpassing the previous best CNN (EfficientNet-L2, 88.4%). Training cost is
roughly 2.5k TPU-days. The model transfers well to CIFAR-10 (99.0%) and
CIFAR-100 (94.6%). Limitation: ViT performs poorly without large-scale
pre-training data — on ImageNet alone (without JFT) it underperforms ResNets.""",
        """{
  "arxiv_id": "2010.11929",
  "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
  "problem": "CNNs dominate image classification but Transformers, which excel in NLP, have not been applied directly to raw image patches at scale.",
  "method": "Images are split into 16×16 non-overlapping patches; each patch is linearly embedded and fed as a token sequence to a standard Transformer encoder pretrained on large image datasets.",
  "dataset": "JFT-300M (300M images, 18k classes) for pre-training; ImageNet-1k (~1.28M images, 1k classes) for fine-tuning; CIFAR-10 and CIFAR-100 for transfer evaluation.",
  "eval_method": "fine-tuned",
  "results": "ViT-L/16 achieves 88.55% top-1 accuracy on ImageNet, outperforming EfficientNet-L2 (88.4%); transfers to 99.0% on CIFAR-10 and 94.6% on CIFAR-100.",
  "contribution": "Demonstrates that a pure Transformer applied to image patches can match or surpass state-of-the-art CNNs when pre-trained on sufficiently large datasets, challenging CNN dominance in vision.",
  "limitations": "Requires very large-scale pre-training data; underperforms ResNets on ImageNet when trained from scratch without JFT.",
  "prerequisites": "Understanding of Transformer self-attention, patch embedding, and transfer learning for image classification.",
  "real_world_impact": "Opens the door to unified vision-language architectures by showing that Transformers can serve as general-purpose vision backbones.",
  "audience": "Computer vision researchers and ML engineers building large-scale image recognition systems",
  "precision": "Not reported",
  "recall": "Not reported",
  "f1_score": "Not reported",
  "accuracy": "88.55% top-1 on ImageNet",
  "auc": "Not reported",
  "bleu": "Not reported",
  "rouge": "Not reported",
  "other_metrics": "CIFAR-10: 99.0%, CIFAR-100: 94.6%",
  "baseline": "EfficientNet-L2 (88.4% top-1 on ImageNet)"
}"""
    ),
]


def _render_examples() -> str:
    """Render FEW_SHOT_EXAMPLES into the prompt string."""
    parts = []
    for i, (excerpt, output_json) in enumerate(FEW_SHOT_EXAMPLES, start=1):
        parts.append(
            f"Example {i}\nInput:\n{excerpt}\n\nExpected Output:\n{output_json}"
        )
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt template — instructions + examples + actual papers
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT_TEMPLATE = """\
You are extracting structured information from machine learning research papers.

For EACH paper provided, extract the following fields. Follow the examples below
exactly — match field names, use "Not reported" for absent metrics, and never
invent numbers not stated in the text.

Fields to extract:
- problem: what problem the paper addresses (1-2 sentences)
- method: the core technical approach (1-2 sentences)
- dataset: dataset name(s) and size if stated, or "Not specified"
- eval_method: "zero-shot", "few-shot", "fine-tuned", "cross-validation", or a short description; "Not specified" if unclear
- results: 1-2 sentence narrative of key findings
- contribution: what is novel versus prior work (1-2 sentences)
- limitations: key weaknesses, stated or reasonably inferred; "Not explicitly discussed" if nothing evident
- prerequisites: background knowledge needed; "None specified" if self-contained
- real_world_impact: ONE short sentence on practical significance
- audience: who this paper is written for, as one short phrase
- precision, recall, f1_score, accuracy, auc, bleu, rouge: ONLY if explicitly stated in the text; "Not reported" otherwise
- other_metrics: any other reported metric not listed above, or "Not reported"
- baseline: name of the baseline model/method the headline result was compared against, or "Not reported"

NEVER estimate or invent numeric values. If a number is not in the text, output "Not reported".

Respond ONLY with a JSON array — no markdown fences, no preamble. Each element
must have exactly these keys:
arxiv_id, title, problem, method, dataset, eval_method, results, contribution,
limitations, prerequisites, real_world_impact, audience, precision, recall,
f1_score, accuracy, auc, bleu, rouge, other_metrics, baseline

========================================
FEW-SHOT EXAMPLES
========================================

{examples}

========================================
Now process the following {count} paper(s) and return ONLY valid JSON.
========================================

PAPERS:
{papers_block}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_papers_block(papers, texts: dict[str, str]) -> str:
    blocks = []
    for p in papers:
        # Use full text — cache prevents re-paying token cost on repeated lookups
        text = texts.get(p.arxiv_id, p.abstract)
        blocks.append(
            "---\narxiv_id: " + p.arxiv_id
            + "\ntitle: " + p.title
            + "\ntext:\n" + text
            + "\n"
        )
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def extract_papers(
    papers,
    texts: dict[str, str],
    semaphore: asyncio.Semaphore | None = None,
) -> list[ExtractedPaper]:
    """
    Async structured extraction with per-paper SQLite caching.

    Papers already in the cache skip the Gemini call entirely.
    Only cache-miss papers are batched into a single Gemini request
    (bounded by the semaphore for concurrency control).
    """
    results: list[ExtractedPaper] = []
    uncached_papers = []

    # --- Stage A: Serve cached extractions ---
    for p in papers:
        cached = cache_service.get_extraction(p.arxiv_id)
        if cached:
            results.append(ExtractedPaper(**cached))
        else:
            uncached_papers.append(p)

    if not uncached_papers:
        logger.info("[extraction] All %d papers served from cache.", len(papers))
        return results

    logger.info(
        "[extraction] %d cache hits, %d cache misses — calling Gemini.",
        len(results), len(uncached_papers),
    )

    # --- Stage B: Batch Gemini call for uncached papers ---
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        examples=_render_examples(),
        count=len(uncached_papers),
        papers_block=_build_papers_block(uncached_papers, texts),
    )

    raw = await gemini_client.call_gemini("extraction", prompt, semaphore)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error("[extraction] JSON parse error: %s\nRaw: %.300s", e, raw)
        raise

    for item in data:
        ep = ExtractedPaper(**item)
        cache_service.set_extraction(ep.arxiv_id, item)
        results.append(ep)

    return results
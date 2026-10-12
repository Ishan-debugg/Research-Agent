"""
Stage 4: Structured extraction via Groq (fast) with Gemini as fallback.

Key features:
  1. FEW-SHOT PROMPTING — 2 high-quality examples in every prompt for schema
     adherence and to prevent hallucinated metric values.

  2. SQLITE CACHE — Each paper's extraction is cached by arxiv_id. Cache hits
     skip the API call entirely (0 tokens consumed).

  3. CONCURRENT PER-PAPER CALLS — extract_papers() fires one Groq call PER
     PAPER, run concurrently via asyncio.gather and bounded by an
     asyncio.Semaphore (GROQ_CONCURRENCY, default: 5). This replaces the old
     "stuff every paper into one giant prompt" approach, which was prone to
     cross-paper contamination (the model mixing up facts between Paper A and
     Paper B). Because calls run in parallel, wall-clock time is roughly the
     time of a SINGLE paper's generation rather than growing with paper count.

  4. DETERMINISTIC TEMPERATURE — temperature=0.0 via groq_client.

  5. TEXT CAPPED AT 8k chars/paper — covers abstract + intro + methods/results
     for most arXiv papers, which is where the extraction fields live.

  6. GRACEFUL DEGRADATION — per-paper try/except in every call. One bad paper
     never kills the entire batch. Failed papers are logged and skipped with
     an error list returned alongside successful extractions.

  Model: Groq llama-3.1-8b-instant (primary), Gemini as fallback.
"""

import asyncio
import json
import logging

from app.models.schemas import ExtractedPaper
from app.services import cache_service
from app.services import groq_client

MODEL_NAME = groq_client._get_groq_model()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

FEW_SHOT_EXAMPLES = [
    (
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
        """arxiv_id: 2010.11929
title: An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale
text:
We split each image into fixed-size 16x16 patches and feed linear embeddings of
those patches as tokens to a standard Transformer encoder. Pre-training on
JFT-300M (300M images, 18k classes) and fine-tuning on ImageNet-1k, our
Vision Transformer (ViT-L/16) achieves 88.55% top-1 accuracy on ImageNet,
surpassing the previous best CNN (EfficientNet-L2, 88.4%). Training cost is
roughly 2.5k TPU-days. The model transfers well to CIFAR-10 (99.0%) and
CIFAR-100 (94.6%). Limitation: ViT performs poorly without large-scale
pre-training data.""",
        """{
  "arxiv_id": "2010.11929",
  "title": "An Image is Worth 16x16 Words: Transformers for Image Recognition at Scale",
  "problem": "CNNs dominate image classification but Transformers have not been applied directly to raw image patches at scale.",
  "method": "Images are split into 16x16 non-overlapping patches; each patch is linearly embedded and fed as a token sequence to a standard Transformer encoder pretrained on large image datasets.",
  "dataset": "JFT-300M (300M images, 18k classes) for pre-training; ImageNet-1k for fine-tuning; CIFAR-10 and CIFAR-100 for transfer evaluation.",
  "eval_method": "fine-tuned",
  "results": "ViT-L/16 achieves 88.55% top-1 accuracy on ImageNet, outperforming EfficientNet-L2 (88.4%); transfers to 99.0% on CIFAR-10 and 94.6% on CIFAR-100.",
  "contribution": "Demonstrates that a pure Transformer applied to image patches can match or surpass state-of-the-art CNNs when pre-trained on sufficiently large datasets.",
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
    parts = []
    for i, (excerpt, output_json) in enumerate(FEW_SHOT_EXAMPLES, start=1):
        parts.append(f"Example {i}\nInput:\n{excerpt}\n\nExpected Output:\n{output_json}")
    return "\n\n---\n\n".join(parts)


# ---------------------------------------------------------------------------
# Prompt template — single-paper focused (used for concurrent per-paper calls)
# ---------------------------------------------------------------------------

SINGLE_PAPER_PROMPT_TEMPLATE = """\
You are extracting structured information from ONE machine learning research paper.

Extract these fields exactly. Follow the examples below — match field names,
use "Not reported" for absent metrics, and never invent numbers not stated in the text.

Fields to extract:
- problem: what problem the paper addresses (1-2 sentences)
- method: the core technical approach (1-2 sentences)
- dataset: dataset name(s) and size if stated, or "Not specified"
- eval_method: "zero-shot", "few-shot", "fine-tuned", "cross-validation", or short description
- results: 1-2 sentence narrative of key findings
- contribution: what is novel versus prior work (1-2 sentences)
- limitations: key weaknesses; "Not explicitly discussed" if nothing evident
- prerequisites: background knowledge needed; "None specified" if self-contained
- real_world_impact: ONE short sentence on practical significance
- audience: who this paper is written for, as one short phrase
- precision, recall, f1_score, accuracy, auc, bleu, rouge: ONLY if explicitly stated; "Not reported" otherwise
- other_metrics: any other reported metric, or "Not reported"
- baseline: baseline model/method compared against, or "Not reported"

NEVER estimate or invent numeric values. If a number is not in the text, output "Not reported".

Respond with a SINGLE JSON object (not an array) — no markdown fences, no preamble.
Keys: arxiv_id, title, problem, method, dataset, eval_method, results, contribution,
limitations, prerequisites, real_world_impact, audience, precision, recall,
f1_score, accuracy, auc, bleu, rouge, other_metrics, baseline

========================================
FEW-SHOT EXAMPLES
========================================

{examples}

========================================
Now process this paper:
========================================

PAPER:
arxiv_id: {arxiv_id}
title: {title}
text:
{text}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# 8k chars covers abstract + intro + most of methods/results for a typical
# arXiv paper, where the fields we extract live. Increased from 3k which
# barely covered the abstract and caused most fields to be "Not reported".
MAX_CHARS_PER_PAPER = 8_000


def _coerce_extraction_item(item: dict) -> dict:
    """Stringify any dict/list values that should be plain strings.

    The LLM occasionally returns nested dicts for fields like 'results' or
    'other_metrics'. Pydantic's field_validator in ExtractedPaper will also
    coerce these, but this helper makes the raw dict clean before storage.
    """
    string_fields = {
        "problem", "method", "dataset", "eval_method", "results", "contribution",
        "limitations", "prerequisites", "real_world_impact", "audience",
        "precision", "recall", "f1_score", "accuracy", "auc",
        "bleu", "rouge", "other_metrics", "baseline",
    }
    cleaned = dict(item)
    for key in string_fields:
        val = cleaned.get(key)
        if val is None:
            cleaned[key] = "Not reported"
        elif isinstance(val, dict):
            cleaned[key] = "; ".join(f"{k}: {v}" for k, v in val.items())
        elif isinstance(val, list):
            cleaned[key] = "; ".join(str(x) for x in val)
        elif not isinstance(val, str):
            cleaned[key] = str(val)
    return cleaned


# ---------------------------------------------------------------------------
# Per-paper extraction (concurrent)
# ---------------------------------------------------------------------------

async def _extract_one(
    paper,
    texts: dict[str, str],
    semaphore: asyncio.Semaphore | None,
) -> tuple["ExtractedPaper | None", dict | None]:
    """
    Extract a single paper with its own dedicated Groq call.
    Never raises — converts all failures to error dicts so asyncio.gather()
    over many of these can't be torpedoed by one bad paper.
    """
    text = texts.get(paper.arxiv_id, paper.abstract)[:MAX_CHARS_PER_PAPER]
    prompt = SINGLE_PAPER_PROMPT_TEMPLATE.format(
        examples=_render_examples(),
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        text=text,
    )

    try:
        raw = await groq_client.call_groq(prompt, semaphore)
    except Exception as e:
        logger.error("[extraction] Groq call failed for %s: %s", paper.arxiv_id, e)
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": str(e)}

    try:
        data = json.loads(groq_client.sanitize_json(raw))
    except json.JSONDecodeError as e:
        logger.error("[extraction] JSON parse error for %s: %s\nRaw: %.300s", paper.arxiv_id, e, raw)
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": f"JSON parse error: {e}"}

    # Solo prompt returns object, but sometimes still wraps in array
    if isinstance(data, list):
        data = data[0] if data else None
    if not data or not isinstance(data, dict):
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": "Empty extraction response"}

    # Ensure arxiv_id matches our paper (model may omit or alter it)
    data["arxiv_id"] = paper.arxiv_id
    data.setdefault("title", paper.title)
    data = _coerce_extraction_item(data)

    try:
        ep = ExtractedPaper(**data)
        cache_service.set_extraction(ep.arxiv_id, data)
        return ep, None
    except Exception as e:
        arxiv_id = data.get("arxiv_id", paper.arxiv_id)
        logger.warning(
            "[extraction] Failed to parse extraction for %s: %s — skipping.",
            arxiv_id, e,
        )
        return None, {
            "arxiv_id": arxiv_id,
            "title": data.get("title", paper.title),
            "error": f"Extraction parse error: {e}",
        }


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------

async def extract_papers(
    papers,
    texts: dict[str, str],
    semaphore: asyncio.Semaphore | None = None,
) -> tuple[list[ExtractedPaper], list[dict]]:
    """
    Async structured extraction with per-paper SQLite caching.

    Papers already in the cache skip the Groq call entirely. Cache-miss
    papers are each extracted with their OWN concurrent Groq call — run in
    parallel via asyncio.gather and bounded by `semaphore` (GROQ_CONCURRENCY,
    default 5) — instead of the old approach of batching every paper into a
    single giant prompt. This avoids cross-paper contamination (the model
    mixing up facts between papers) and, because the calls run in parallel,
    typically finishes in roughly the time of ONE paper's generation rather
    than growing with the number of papers.

    Returns:
        Tuple of (successful_extractions, errors) where errors is a list of
        {"arxiv_id": ..., "error": ...} dicts for papers that failed extraction.
    """
    results: list[ExtractedPaper] = []
    errors: list[dict] = []
    uncached_papers = []

    # --- Stage A: Serve cached extractions ---
    for p in papers:
        cached = cache_service.get_extraction(p.arxiv_id)
        if cached:
            try:
                results.append(ExtractedPaper(**cached))
            except Exception as e:
                logger.warning("[extraction] Cached data invalid for %s: %s", p.arxiv_id, e)
                uncached_papers.append(p)
        else:
            uncached_papers.append(p)

    if not uncached_papers:
        logger.info("[extraction] All %d papers served from cache.", len(papers))
        return results, errors

    logger.info(
        "[extraction] %d cache hits, %d cache misses — firing %d concurrent per-paper Groq calls.",
        len(results), len(uncached_papers), len(uncached_papers),
    )

    # --- Stage B: One concurrent Groq call PER paper, bounded by semaphore ---
    outcomes = await asyncio.gather(
        *[_extract_one(p, texts, semaphore) for p in uncached_papers]
    )

    for ep, err in outcomes:
        if ep is not None:
            results.append(ep)
        elif err is not None:
            errors.append(err)

    if errors:
        logger.warning(
            "[extraction] %d/%d papers extracted successfully, %d failed.",
            len(results), len(papers), len(errors),
        )
    else:
        logger.info("[extraction] All %d papers extracted successfully.", len(results))

    return results, errors
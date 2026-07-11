"""
Stage 4: Structured extraction via Groq Mixtral (fast) with Gemini as fallback.

Key features:
  1. FEW-SHOT PROMPTING — 2 high-quality examples in every prompt for schema
     adherence and to prevent hallucinated metric values.

  2. SQLITE CACHE — Each paper's extraction is cached by arxiv_id. Cache hits
     skip the API call entirely (0 tokens consumed).

  3. SMART BATCH + PER-PAPER FALLBACK:
     a. All cache-miss papers are sent in ONE batched call (fast path).
     b. Any paper omitted from the batch response is retried individually.
        This guarantees no paper is silently dropped.
     c. ID matching is fuzzy (strips version suffix).

  4. DETERMINISTIC TEMPERATURE — temperature=0.0 via groq_client.

  5. TEXT CAPPED AT 8k chars/paper.

  6. GRACEFUL DEGRADATION — per-paper try/except in the parse loop.

  Model: Groq Mixtral-8x7b (3-4x faster than Gemini flash for extraction).
  Graph synthesis remains on Gemini 2.5 Pro (see graph_service.py).
"""

import asyncio
import json
import logging

import google.generativeai as genai

from app.models.schemas import ExtractedPaper
from app.services import cache_service
from app.services import gemini_client
from app.services import groq_client

MODEL_NAME = groq_client.GROQ_MODEL

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
# Prompt templates — one for batch, one for single paper
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT_TEMPLATE = """\
You are extracting structured information from machine learning research papers.

For EACH paper provided, extract the following fields. Follow the examples below
exactly — match field names, use "Not reported" for absent metrics, and never
invent numbers not stated in the text.

IMPORTANT: You MUST return one JSON object for EVERY paper listed. Do NOT skip
any paper. If you cannot find a field, use "Not reported" or "Not specified".

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

Respond ONLY with a JSON array containing exactly {count} objects — no markdown fences, no preamble.
Each element must have exactly these keys:
arxiv_id, title, problem, method, dataset, eval_method, results, contribution,
limitations, prerequisites, real_world_impact, audience, precision, recall,
f1_score, accuracy, auc, bleu, rouge, other_metrics, baseline

========================================
FEW-SHOT EXAMPLES
========================================

{examples}

========================================
Now process ALL {count} paper(s) below. Return EXACTLY {count} JSON objects.
========================================

PAPERS:
{papers_block}
"""

# Simpler single-paper prompt for individual retries — no array, just one object
SINGLE_PAPER_PROMPT_TEMPLATE = """\
You are extracting structured information from ONE machine learning research paper.

Extract these fields exactly. Use "Not reported" for missing metrics.
Never invent numeric values.

Fields: problem, method, dataset, eval_method, results, contribution,
limitations, prerequisites, real_world_impact, audience, precision, recall,
f1_score, accuracy, auc, bleu, rouge, other_metrics, baseline

Respond with a SINGLE JSON object (not an array).

PAPER:
arxiv_id: {arxiv_id}
title: {title}
text:
{text}
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_CHARS_PER_PAPER = 8_000


def _base_id(arxiv_id: str) -> str:
    """Strip version suffix for fuzzy matching: '2301.12345v2' → '2301.12345'."""
    return arxiv_id.split("v")[0] if "v" in arxiv_id else arxiv_id


def _build_papers_block(papers, texts: dict[str, str]) -> str:
    blocks = []
    for p in papers:
        text = texts.get(p.arxiv_id, p.abstract)
        truncated = text[:MAX_CHARS_PER_PAPER]
        blocks.append(
            "---\narxiv_id: " + p.arxiv_id
            + "\ntitle: " + p.title
            + "\ntext:\n" + truncated
            + "\n"
        )
    return "\n".join(blocks)


# ---------------------------------------------------------------------------
# Single-paper fallback extractor
# ---------------------------------------------------------------------------

async def _extract_one_solo(
    paper,
    texts: dict[str, str],
    semaphore: asyncio.Semaphore | None,
) -> tuple["ExtractedPaper | None", dict | None]:
    """
    Extract a single paper with its own dedicated Gemini call.
    Used as fallback when the batch call omits a paper.
    Never raises — converts all failures to error dicts.
    """
    text = texts.get(paper.arxiv_id, paper.abstract)[:MAX_CHARS_PER_PAPER]
    prompt = SINGLE_PAPER_PROMPT_TEMPLATE.format(
        arxiv_id=paper.arxiv_id,
        title=paper.title,
        text=text,
    )

    try:
        raw = await groq_client.call_groq(prompt, semaphore)
    except Exception as e:
        logger.error("[extraction] Solo retry failed for %s: %s", paper.arxiv_id, e)
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": str(e)}

    try:
        data = json.loads(groq_client.sanitize_json(raw))
    except json.JSONDecodeError as e:
        logger.error("[extraction] Solo JSON parse error for %s: %s", paper.arxiv_id, e)
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": f"JSON parse error: {e}"}

    # Normalise: solo prompt returns object, but sometimes still wraps in array
    if isinstance(data, list):
        data = data[0] if data else None
    if not data or not isinstance(data, dict):
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": "Empty solo response"}

    # Ensure arxiv_id matches our paper (model may omit or alter it)
    data["arxiv_id"] = paper.arxiv_id
    data.setdefault("title", paper.title)

    try:
        ep = ExtractedPaper(**data)
        cache_service.set_extraction(ep.arxiv_id, data)
        logger.info("[extraction] Solo retry SUCCESS for %s", paper.arxiv_id)
        return ep, None
    except Exception as e:
        logger.warning("[extraction] Solo parse error for %s: %s", paper.arxiv_id, e)
        return None, {"arxiv_id": paper.arxiv_id, "title": paper.title, "error": f"Parse error: {e}"}


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

    Strategy:
      1. Cache hits → instant (0 Gemini calls).
      2. Cache misses → ONE batched Gemini call (all papers in one prompt).
      3. Any paper Gemini omits from its batch response → individual retry call.
         This guarantees no paper is silently dropped.

    Returns (successful_extractions, errors).
    """
    results: list[ExtractedPaper] = []
    errors: list[dict] = []
    uncached_papers = []

    # ── Stage A: Serve cached extractions ────────────────────────────────────
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
        "[extraction] %d cache hits, %d cache misses — batched call for %d papers.",
        len(results), len(uncached_papers), len(uncached_papers),
    )

    # ── Stage B: Single batched Gemini call ──────────────────────────────────
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(
        examples=_render_examples(),
        count=len(uncached_papers),
        papers_block=_build_papers_block(uncached_papers, texts),
    )

    batch_failed_all = False
    returned_data: list[dict] = []

    try:
        raw = await groq_client.call_groq(prompt, semaphore)
        data = json.loads(groq_client.sanitize_json(raw))
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            returned_data = [item for item in data if isinstance(item, dict)]
        else:
            logger.error("[extraction] Unexpected batch response shape: %s", type(data))
            batch_failed_all = True
    except Exception as e:
        logger.error("[extraction] Batched Groq call failed: %s", e)
        batch_failed_all = True

    # ── Stage C: Parse batch results ─────────────────────────────────────────
    # Build fuzzy ID lookup: base_id → paper object (handles version suffixes)
    paper_by_base_id = {_base_id(p.arxiv_id): p for p in uncached_papers}
    successfully_extracted_ids: set[str] = set()

    for item in returned_data:
        raw_id   = item.get("arxiv_id", "")
        # Try exact match first, then base-id fuzzy match
        paper = (
            next((p for p in uncached_papers if p.arxiv_id == raw_id), None)
            or paper_by_base_id.get(_base_id(raw_id))
        )
        if paper:
            item["arxiv_id"] = paper.arxiv_id   # normalise to our canonical ID
        item.setdefault("title", paper.title if paper else raw_id)

        try:
            ep = ExtractedPaper(**item)
            cache_service.set_extraction(ep.arxiv_id, item)
            results.append(ep)
            successfully_extracted_ids.add(ep.arxiv_id)
        except Exception as e:
            arxiv_id = item.get("arxiv_id", raw_id)
            logger.warning("[extraction] Parse error for %s: %s", arxiv_id, e)
            errors.append({"arxiv_id": arxiv_id, "title": item.get("title", ""), "error": f"Parse error: {e}"})

    # ── Stage D: Retry papers Gemini omitted from the batch ──────────────────
    missing = [
        p for p in uncached_papers
        if p.arxiv_id not in successfully_extracted_ids
    ]

    if missing:
        if batch_failed_all:
            logger.warning(
                "[extraction] Batch call failed entirely — retrying all %d papers individually.", len(missing)
            )
        else:
            logger.warning(
                "[extraction] Batch omitted %d/%d papers — retrying individually: %s",
                len(missing), len(uncached_papers),
                [p.arxiv_id for p in missing],
            )

        # Run individual retries concurrently (bounded by semaphore)
        retry_outcomes = await asyncio.gather(
            *[_extract_one_solo(p, texts, semaphore) for p in missing]
        )
        for ep, err in retry_outcomes:
            if ep is not None:
                results.append(ep)
            elif err is not None:
                errors.append(err)

    if errors:
        logger.warning(
            "[extraction] Final: %d/%d papers extracted, %d failed.",
            len(results), len(papers), len(errors),
        )
    else:
        logger.info("[extraction] All %d papers extracted successfully.", len(results))

    return results, errors
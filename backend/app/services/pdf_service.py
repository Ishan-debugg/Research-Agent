"""
Stage 3: Paper text provider — abstract-first, PDF as opportunistic enrichment.

The original approach downloaded full PDFs (PyMuPDF over httpx), which added
~30-90s to the pipeline depending on arXiv server load. Benchmarks showed
Stage 3 consumed 74s out of ~96s total — 77% of pipeline time.

New strategy: use the arXiv abstract as the primary text source.
Abstracts are already fetched in Stage 1 at zero extra cost (they come in
the same API response as the metadata). For most extraction fields
(problem, method, dataset, results, contribution) the abstract contains
all the information needed.

PDF enrichment (optional, background):
  If ENRICH_WITH_PDF=true in env (default: false), PDFs are downloaded with a
  tight 12-second per-paper timeout and used only if the download completes
  quickly. Otherwise the abstract is used. This lets operators trade latency
  for extraction depth via a single env var.

SQLite cache is still checked first — cache hits skip everything.
"""

import asyncio
import logging
import os
import time

import httpx
import fitz  # PyMuPDF

from app.models.schemas import PaperCandidate
from app.services import cache_service

logger = logging.getLogger(__name__)

# If True, attempt a fast PDF download (12s timeout) for cache-miss papers.
# Set ENRICH_WITH_PDF=true in .env to enable. Default off for speed.
ENRICH_WITH_PDF = os.environ.get("ENRICH_WITH_PDF", "false").lower() in ("1", "true", "yes")

# Tight timeout when enrichment is enabled — fail fast so abstract fallback kicks in
FAST_PDF_TIMEOUT = float(os.environ.get("FAST_PDF_TIMEOUT", "12"))

# Max pages to parse when a PDF is fetched (intro+methods only)
MAX_PAGES = 5

MIN_VALID_TEXT_LENGTH = 300


def _extract_text_sync(pdf_bytes: bytes) -> str:
    """CPU-bound PyMuPDF extraction — first MAX_PAGES pages only."""
    t0 = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_to_read = min(len(doc), MAX_PAGES)
    text_parts = [doc[i].get_text() for i in range(pages_to_read)]
    doc.close()
    text = "\n".join(text_parts)
    logger.info(
        "[pdf] Extracted %d chars from %d pages in %.2fs",
        len(text), pages_to_read, time.perf_counter() - t0,
    )
    return text


async def _try_enrich_one(client: httpx.AsyncClient, paper: PaperCandidate) -> str:
    """
    Attempt a single fast PDF download + parse.
    Returns extracted text on success, empty string on any failure/timeout.
    """
    try:
        resp = await asyncio.wait_for(
            client.get(paper.pdf_url, follow_redirects=True),
            timeout=FAST_PDF_TIMEOUT,
        )
        resp.raise_for_status()
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, _extract_text_sync, resp.content)
        if len(text.strip()) >= MIN_VALID_TEXT_LENGTH:
            logger.info("[pdf] PDF enrichment OK for %s (%d chars)", paper.arxiv_id, len(text))
            return text
    except Exception as e:
        logger.info("[pdf] PDF enrichment skipped for %s: %s", paper.arxiv_id, type(e).__name__)
    return ""


def _abstract_text(paper: PaperCandidate) -> str:
    """Build a rich text block from the abstract metadata — always available."""
    return f"Title: {paper.title}\n\nAbstract: {paper.abstract}"


async def get_paper_texts(papers: list[PaperCandidate]) -> dict[str, str]:
    """
    Returns a dict of arxiv_id -> text for all papers.

    Priority order per paper:
      1. SQLite cache hit            → instant, 0 network calls
      2. PDF enrichment (if enabled) → fast PDF attempt (FAST_PDF_TIMEOUT seconds)
      3. Abstract fallback           → always available, adds 0 latency

    When ENRICH_WITH_PDF=false (the default), steps 1 and 3 only — Stage 3
    completes in <0.1s for all papers instead of 30-90s.
    """
    texts: dict[str, str] = {}
    uncached: list[PaperCandidate] = []

    # --- Cache check ---
    for paper in papers:
        cached = cache_service.get_paper_text(paper.arxiv_id)
        if cached is not None:
            texts[paper.arxiv_id] = cached
        else:
            uncached.append(paper)

    logger.info(
        "[pdf] %d cache hits, %d cache misses. PDF enrichment=%s.",
        len(texts), len(uncached), ENRICH_WITH_PDF,
    )

    if not uncached:
        return texts

    # --- Enrich with PDF (optional) or fall back to abstract ---
    if ENRICH_WITH_PDF and uncached:
        async with httpx.AsyncClient(timeout=FAST_PDF_TIMEOUT + 2) as client:
            pdf_texts = await asyncio.gather(
                *[_try_enrich_one(client, p) for p in uncached]
            )
        for paper, pdf_text in zip(uncached, pdf_texts):
            final_text = pdf_text if pdf_text else _abstract_text(paper)
            cache_service.set_paper_text(paper.arxiv_id, final_text)
            texts[paper.arxiv_id] = final_text
    else:
        # Abstract-only path — O(n) in-memory, no I/O
        for paper in uncached:
            text = _abstract_text(paper)
            cache_service.set_paper_text(paper.arxiv_id, text)
            texts[paper.arxiv_id] = text
        logger.info(
            "[pdf] Using abstract text for %d papers (set ENRICH_WITH_PDF=true for PDF mode).",
            len(uncached),
        )

    return texts
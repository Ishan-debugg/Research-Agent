"""
Stage 3: Download PDFs and extract text with PyMuPDF.

Key improvements over the original:
  1. SQLITE CACHE — Before downloading, each paper's arxiv_id is checked
     against the cache. Cache hits skip the HTTP download and PyMuPDF
     parse entirely, saving ~2–10 s per paper.

  2. TIMING LOGS — Per-paper download and extraction time is logged so
     bottlenecks are immediately visible in the uvicorn terminal.

  3. RETRY with BACKOFF — Downloads retry up to 2 times with a 3s wait
     to handle transient arXiv CDN failures.

  4. EXTENDED TIMEOUT — 30s timeout (up from 15s) to accommodate slow
     arXiv CDN responses during peak hours.

Original safeguards preserved:
  - Async/concurrent downloads via asyncio.gather
  - Fallback to abstract-only text when PDF extraction fails
"""

import asyncio
import io
import logging
import time

import httpx
import fitz  # PyMuPDF

from app.models.schemas import PaperCandidate
from app.services import cache_service

logger = logging.getLogger(__name__)

MIN_VALID_TEXT_LENGTH = 500  # below this, treat extraction as failed
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY_SECONDS = 3.0
DOWNLOAD_TIMEOUT_SECONDS = 30.0
PER_PAPER_TIMEOUT_SECONDS = 90.0  # max total time per paper (download + extract)


async def _download_pdf(client: httpx.AsyncClient, url: str) -> bytes | None:
    """Download PDF with retry and extended timeout."""
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            resp = await client.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
            resp.raise_for_status()
            elapsed = time.perf_counter() - t0
            logger.info(
                "[pdf] Downloaded %.0f KB in %.1fs — %s",
                len(resp.content) / 1024, elapsed, url,
            )
            return resp.content
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if attempt < MAX_DOWNLOAD_RETRIES:
                logger.warning(
                    "[pdf] Download attempt %d/%d failed (%.1fs): %s — %s  Retrying in %.0fs...",
                    attempt, MAX_DOWNLOAD_RETRIES, elapsed,
                    type(e).__name__, url, RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.warning(
                    "[pdf] Download FAILED after %d attempts (%.1fs): %s — %s",
                    MAX_DOWNLOAD_RETRIES, elapsed, type(e).__name__, url,
                )
    return None


def _extract_text(pdf_bytes: bytes, max_pages: int = 10) -> str:
    """
    Extract text from the first N pages only.
    Intro, methods, and most results sections live early in arXiv papers;
    capping pages keeps token usage manageable for the Gemini step.
    """
    t0 = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_to_read = min(len(doc), max_pages)
    text_parts = [doc[i].get_text() for i in range(pages_to_read)]
    doc.close()
    text = "\n".join(text_parts)
    logger.info("[pdf] Extracted %d chars from %d pages in %.2fs", len(text), pages_to_read, time.perf_counter() - t0)
    return text


async def get_paper_texts(papers: list[PaperCandidate]) -> dict[str, str]:
    """
    Returns a dict of arxiv_id -> text.

    Workflow per paper:
      1. Check SQLite cache — if hit, return immediately (no download).
      2. If miss, download PDF concurrently with other misses.
      3. Extract text with PyMuPDF; fall back to abstract on failure.
      4. Store extracted text in SQLite cache for future requests.
    """
    cached_texts: dict[str, str] = {}
    uncached_papers: list[PaperCandidate] = []

    # --- Stage A: Serve from cache ---
    for paper in papers:
        cached = cache_service.get_paper_text(paper.arxiv_id)
        if cached is not None:
            cached_texts[paper.arxiv_id] = cached
        else:
            uncached_papers.append(paper)

    logger.info(
        "[pdf] %d text cache hits, %d downloads needed.",
        len(cached_texts), len(uncached_papers),
    )

    if not uncached_papers:
        return cached_texts

    # --- Stage B: Download uncached PDFs concurrently (each with a per-paper timeout) ---
    async with httpx.AsyncClient() as client:
        async def _download_with_timeout(paper):
            try:
                return await asyncio.wait_for(
                    _download_pdf(client, paper.pdf_url),
                    timeout=PER_PAPER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[pdf] Per-paper timeout (%.0fs) exceeded for %s — using abstract fallback.",
                    PER_PAPER_TIMEOUT_SECONDS, paper.arxiv_id,
                )
                return None

        pdf_bytes_list = await asyncio.gather(
            *[_download_with_timeout(p) for p in uncached_papers]
        )

    # --- Stage C: Extract text and populate cache ---
    fresh_texts: dict[str, str] = {}
    for paper, pdf_bytes in zip(uncached_papers, pdf_bytes_list):
        text = ""
        if pdf_bytes:
            try:
                text = _extract_text(pdf_bytes)
            except Exception as e:
                logger.warning("[pdf] PyMuPDF extraction failed for %s: %s", paper.arxiv_id, e)
                text = ""

        if len(text.strip()) < MIN_VALID_TEXT_LENGTH:
            # Fallback: abstract-only is still useful for Gemini extraction
            text = f"Title: {paper.title}\n\nAbstract: {paper.abstract}"
            logger.info("[pdf] Using abstract fallback for %s", paper.arxiv_id)

        cache_service.set_paper_text(paper.arxiv_id, text)
        fresh_texts[paper.arxiv_id] = text

    return {**cached_texts, **fresh_texts}
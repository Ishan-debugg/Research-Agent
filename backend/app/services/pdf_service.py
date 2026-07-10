"""
Stage 3: Download PDFs and extract text with PyMuPDF.

Change from original: _extract_text (CPU-bound PyMuPDF parsing) now runs
in run_in_executor instead of blocking the event loop synchronously after
the async downloads complete.
"""

import asyncio
import logging
import time

import httpx
import fitz  # PyMuPDF

from app.models.schemas import PaperCandidate
from app.services import cache_service

logger = logging.getLogger(__name__)

MIN_VALID_TEXT_LENGTH = 500
MAX_DOWNLOAD_RETRIES = 3
RETRY_DELAY_SECONDS = 3.0
DOWNLOAD_TIMEOUT_SECONDS = 30.0
PER_PAPER_TIMEOUT_SECONDS = 90.0


async def _download_pdf(client: httpx.AsyncClient, url: str) -> bytes | None:
    for attempt in range(1, MAX_DOWNLOAD_RETRIES + 1):
        t0 = time.perf_counter()
        try:
            resp = await client.get(url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True)
            resp.raise_for_status()
            logger.info(
                "[pdf] Downloaded %.0f KB in %.1fs — %s",
                len(resp.content) / 1024, time.perf_counter() - t0, url,
            )
            return resp.content
        except Exception as e:
            elapsed = time.perf_counter() - t0
            if attempt < MAX_DOWNLOAD_RETRIES:
                logger.warning(
                    "[pdf] Download attempt %d/%d failed (%.1fs): %s — retrying in %.0fs...",
                    attempt, MAX_DOWNLOAD_RETRIES, elapsed, type(e).__name__, RETRY_DELAY_SECONDS,
                )
                await asyncio.sleep(RETRY_DELAY_SECONDS)
            else:
                logger.warning(
                    "[pdf] Download FAILED after %d attempts (%.1fs): %s — %s",
                    MAX_DOWNLOAD_RETRIES, elapsed, type(e).__name__, url,
                )
    return None


def _extract_text_sync(pdf_bytes: bytes, max_pages: int = 10) -> str:
    """CPU-bound PyMuPDF extraction — runs in a thread pool executor."""
    t0 = time.perf_counter()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_to_read = min(len(doc), max_pages)
    text_parts = [doc[i].get_text() for i in range(pages_to_read)]
    doc.close()
    text = "\n".join(text_parts)
    logger.info(
        "[pdf] Extracted %d chars from %d pages in %.2fs",
        len(text), pages_to_read, time.perf_counter() - t0,
    )
    return text


async def get_paper_texts(papers: list[PaperCandidate]) -> dict[str, str]:
    """
    Returns a dict of arxiv_id -> text.

    Workflow per paper:
      1. Check SQLite cache — cache hit skips download entirely.
      2. Download PDFs concurrently (async).
      3. Extract text with PyMuPDF in thread pool (CPU-bound, no longer blocks loop).
      4. Store in SQLite cache.
    """
    cached_texts: dict[str, str] = {}
    uncached_papers: list[PaperCandidate] = []

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

    # --- Stage B: Concurrent async downloads ---
    async with httpx.AsyncClient() as client:
        async def _download_with_timeout(paper):
            try:
                return await asyncio.wait_for(
                    _download_pdf(client, paper.pdf_url),
                    timeout=PER_PAPER_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "[pdf] Per-paper timeout exceeded for %s — using abstract fallback.",
                    paper.arxiv_id,
                )
                return None

        pdf_bytes_list = await asyncio.gather(
            *[_download_with_timeout(p) for p in uncached_papers]
        )

    # --- Stage C: Extract text in executor (CPU-bound, non-blocking) ---
    loop = asyncio.get_running_loop()
    fresh_texts: dict[str, str] = {}

    async def _extract_one(paper: PaperCandidate, pdf_bytes: bytes | None) -> tuple[str, str]:
        text = ""
        if pdf_bytes:
            try:
                # Run CPU-bound PyMuPDF in thread pool — no longer blocks event loop
                text = await loop.run_in_executor(None, _extract_text_sync, pdf_bytes)
            except Exception as e:
                logger.warning("[pdf] PyMuPDF extraction failed for %s: %s", paper.arxiv_id, e)

        if len(text.strip()) < MIN_VALID_TEXT_LENGTH:
            text = f"Title: {paper.title}\n\nAbstract: {paper.abstract}"
            logger.info("[pdf] Using abstract fallback for %s", paper.arxiv_id)

        return paper.arxiv_id, text

    # Run all extractions concurrently (each in its own executor thread)
    extract_tasks = [
        _extract_one(paper, pdf_bytes)
        for paper, pdf_bytes in zip(uncached_papers, pdf_bytes_list)
    ]
    extracted_pairs = await asyncio.gather(*extract_tasks)

    for arxiv_id, text in extracted_pairs:
        cache_service.set_paper_text(arxiv_id, text)
        fresh_texts[arxiv_id] = text

    return {**cached_texts, **fresh_texts}
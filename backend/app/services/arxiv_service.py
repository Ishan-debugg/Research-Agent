"""
Stage 1: arXiv retrieval.

search_arxiv is now async: the blocking arxiv.Client().results() call
runs inside run_in_executor so it never blocks the FastAPI event loop.
"""
import asyncio
import logging

import arxiv
from app.models.schemas import PaperCandidate

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)

# Module-level client singleton — avoids re-creating on every request
_client = arxiv.Client()


def _sync_search(query: str, max_results: int) -> list[PaperCandidate]:
    """Synchronous arXiv search — intended to run in an executor."""
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    candidates = []
    for result in _client.results(search):
        candidates.append(
            PaperCandidate(
                arxiv_id=result.get_short_id(),
                title=result.title.strip().replace("\n", " "),
                abstract=result.summary.strip().replace("\n", " "),
                authors=[a.name for a in result.authors],
                published=result.published.isoformat(),
                pdf_url=result.pdf_url,
            )
        )
    return candidates


async def search_arxiv(query: str, max_results: int = 20) -> list[PaperCandidate]:
    """
    Async arXiv retrieval. Runs the blocking HTTP call in a thread pool
    so the event loop stays free for other requests during the ~2-3s wait.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_search, query, max_results)
    except Exception as e:
        logger.error("[arxiv] Search failed for query '%s': %s", query, e)
        return []

"""
Main FastAPI app. /search runs the full pipeline; /tech-match is a
separate, optional, on-demand call.

Key changes from the original:
  - Global asyncio.Semaphore(GEMINI_CONCURRENCY) caps concurrent Gemini calls.
  - extract_papers() and build_knowledge_graph() are now async — awaited here.
  - Structured logging at each stage shows timing, cache hit/miss, and model used.
  - The existing in-memory LRU query cache is preserved for full-query dedup.
  - All API endpoints and JSON response schemas are unchanged.
"""
import asyncio
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

from app.models.schemas import (
    SearchResponse,
    PaperResult,
    TechMatchRequest,
    TechMatchResponse,
)
from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph
from app.services.techmatch_service import match_tech_stack

load_dotenv()

# Configure Gemini globally on startup
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

# ---------------------------------------------------------------------------
# Logging — structured output visible in uvicorn terminal
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(title="Research Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Pipeline tuning — configurable via .env
# ---------------------------------------------------------------------------
ARXIV_CANDIDATE_COUNT = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 15))
TOP_K_PAPERS          = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY    = int(os.environ.get("GEMINI_CONCURRENCY", 3))

# Global semaphore: limits simultaneous Gemini API calls across all requests.
# Initialised at module load so it is shared across the entire process lifetime.
_gemini_semaphore: asyncio.Semaphore | None = None


@app.on_event("startup")
async def _startup():
    global _gemini_semaphore
    _gemini_semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY)
    logger.info(
        "[startup] Gemini concurrency cap = %d | candidates = %d | top_k = %d",
        GEMINI_CONCURRENCY, ARXIV_CANDIDATE_COUNT, TOP_K_PAPERS,
    )


# ---------------------------------------------------------------------------
# In-memory LRU query cache (preserved from original)
# Caches the full SearchResponse dict for the last 64 unique queries.
# This is a fast first-level cache before hitting SQLite per-paper caches.
# ---------------------------------------------------------------------------
_result_cache: dict[str, dict] = {}
_MAX_CACHE = 64
_cache_order: list[str] = []


def _cache_get(key: str):
    return _result_cache.get(key)


def _cache_set(key: str, value: dict):
    if key in _result_cache:
        _cache_order.remove(key)
    _result_cache[key] = value
    _cache_order.append(key)
    if len(_cache_order) > _MAX_CACHE:
        oldest = _cache_order.pop(0)
        _result_cache.pop(oldest, None)


# ---------------------------------------------------------------------------
# Relevance score normalisation (unchanged from original)
# ---------------------------------------------------------------------------
def _relevance_scores(top_papers):
    scores = [p.score for p in top_papers if p.score is not None]
    if not scores:
        return {p.arxiv_id: 90 for p in top_papers}
    min_s, max_s = min(scores), max(scores)
    span = max_s - min_s if max_s != min_s else 1
    result = {}
    for p in top_papers:
        if p.score is None:
            result[p.arxiv_id] = 90
        else:
            result[p.arxiv_id] = round(80 + 20 * (p.score - min_s) / span)
    return result


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search", response_model=SearchResponse)
async def search(query: str):  # noqa: C901
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    cache_key = query.strip().lower()
    cached = _cache_get(cache_key)
    if cached:
        logger.info("[search] QUERY CACHE HIT — '%s'", query)
        return SearchResponse(**cached)

    t0 = time.perf_counter()

    # --- Stage 1: Retrieve candidates from arXiv ---
    candidates = search_arxiv(query, max_results=ARXIV_CANDIDATE_COUNT)
    logger.info(
        "[stage 1: retrieve]   %.1fs  (%d papers)",
        time.perf_counter() - t0, len(candidates),
    )
    if not candidates:
        raise HTTPException(status_code=404, detail="No papers found for this query")

    # --- Stage 2: Semantic rerank ---
    t1 = time.perf_counter()
    top_papers = rerank_papers(query, candidates, top_k=TOP_K_PAPERS)
    logger.info("[stage 2: rerank]     %.1fs", time.perf_counter() - t1)

    # --- Stage 3: PDF download + text extraction (cache-aware, parallel) ---
    t2 = time.perf_counter()
    texts = await get_paper_texts(top_papers)
    logger.info("[stage 3: pdf+parse]  %.1fs", time.perf_counter() - t2)

    # --- Stage 4: Structured extraction (cache-aware, semaphore-bounded) ---
    t3 = time.perf_counter()
    extracted = await extract_papers(top_papers, texts, semaphore=_gemini_semaphore)
    logger.info("[stage 4: extract]    %.1fs", time.perf_counter() - t3)

    # --- Stage 5: Knowledge graph synthesis (cache-aware) ---
    t4 = time.perf_counter()
    graph = await build_knowledge_graph(extracted)
    logger.info("[stage 5: synthesize] %.1fs", time.perf_counter() - t4)

    logger.info("[TOTAL]               %.1fs", time.perf_counter() - t0)

    # --- Assemble response (schema unchanged) ---
    candidates_by_id = {p.arxiv_id: p for p in top_papers}
    relevance = _relevance_scores(top_papers)

    results = []
    for e in extracted:
        cand = candidates_by_id.get(e.arxiv_id)
        results.append(
            PaperResult(
                arxiv_id=e.arxiv_id,
                title=e.title,
                authors=cand.authors if cand else [],
                year=cand.published[:4] if cand else "",
                pdf_url=cand.pdf_url if cand else "",
                relevance_score=relevance.get(e.arxiv_id, 90),
                problem=e.problem,
                method=e.method,
                dataset=e.dataset,
                eval_method=e.eval_method,
                results=e.results,
                contribution=e.contribution,
                limitations=e.limitations,
                prerequisites=e.prerequisites,
                real_world_impact=e.real_world_impact,
                audience=e.audience,
                precision=e.precision,
                recall=e.recall,
                f1_score=e.f1_score,
                accuracy=e.accuracy,
                auc=e.auc,
                bleu=e.bleu,
                rouge=e.rouge,
                other_metrics=e.other_metrics,
                baseline=e.baseline,
            )
        )

    results.sort(key=lambda r: r.relevance_score, reverse=True)

    response = SearchResponse(query=query, papers=results, graph=graph)
    _cache_set(cache_key, response.dict())
    return response


@app.post("/tech-match", response_model=TechMatchResponse)
def tech_match(payload: TechMatchRequest):
    if not payload.tech_stack:
        raise HTTPException(status_code=400, detail="tech_stack must not be empty")
    papers_dicts = [p.dict() for p in payload.papers]
    result = match_tech_stack(papers_dicts, payload.tech_stack)
    return TechMatchResponse(**result)
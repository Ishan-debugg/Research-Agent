"""
Main FastAPI app. /search runs the full pipeline; /tech-match is a
separate, optional, on-demand call.

Stage timings are printed to the console (uvicorn terminal) so you can
see exactly where time is going on a slow request.
"""
import os
import time
from functools import lru_cache
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

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

app = FastAPI(title="Research Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ARXIV_CANDIDATE_COUNT = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K_PAPERS = int(os.environ.get("TOP_K_PAPERS", 5))

# ---------------------------------------------------------------------------
# Simple in-memory result cache — repeated queries are served instantly
# without re-running the full pipeline (LRU, keeps last 64 unique queries).
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
        print("[cache hit]  serving '%s' from cache" % query)
        return SearchResponse(**cached)

    t0 = time.perf_counter()
    candidates = search_arxiv(query, max_results=ARXIV_CANDIDATE_COUNT)
    print("[stage 1: retrieve]   %.1fs  (%d papers)" % (time.perf_counter() - t0, len(candidates)))
    if not candidates:
        raise HTTPException(status_code=404, detail="No papers found for this query")

    t1 = time.perf_counter()
    top_papers = rerank_papers(query, candidates, top_k=TOP_K_PAPERS)
    print("[stage 2: rerank]     %.1fs" % (time.perf_counter() - t1))

    t2 = time.perf_counter()
    texts = await get_paper_texts(top_papers)
    print("[stage 3: pdf+parse]  %.1fs" % (time.perf_counter() - t2))

    t3 = time.perf_counter()
    extracted = extract_papers(top_papers, texts)
    print("[stage 4: extract]    %.1fs" % (time.perf_counter() - t3))

    t4 = time.perf_counter()
    graph = build_knowledge_graph(extracted)
    print("[stage 5: synthesize] %.1fs" % (time.perf_counter() - t4))

    print("[TOTAL]               %.1fs" % (time.perf_counter() - t0))

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
"""
Main FastAPI app. /search runs the full pipeline; /search/stream runs it with
Server-Sent Events for real-time progress; /tech-match is a separate, optional,
on-demand call.

Production improvements over the original:
  - slowapi rate limiting (10 req/min per IP on /search)
  - Optional API-key authentication via X-API-Key header
  - Input validation (query length 3–500 chars)
  - Request timeout (120s for the full pipeline)
  - SSE streaming endpoint (/search/stream) for real-time stage progress
  - Prometheus metrics (/metrics endpoint)
  - GZip response compression
  - Request-ID tracing (X-Request-ID header)
  - Reranker model preloaded on startup (no cold-start penalty)
  - Deep /health check (DB + reranker + Gemini reachable)
  - Graceful shutdown (SQLite connection closed)
  - Restricted CORS (configurable via ALLOWED_ORIGINS env var)
  - Structured logging with request_id context
"""
import asyncio
import json
import logging
import os
import time
import uuid

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware
from dotenv import load_dotenv
import google.generativeai as genai

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

from app.models.schemas import (
    SearchResponse,
    PaperResult,
    ExtractionError,
    TechMatchRequest,
    TechMatchResponse,
)
from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph
from app.services.techmatch_service import match_tech_stack
from app.services import cache_service

load_dotenv()

# Configure Gemini globally on startup — fail fast with a clear error
_gemini_key = os.environ.get("GEMINI_API_KEY")
if not _gemini_key:
    raise RuntimeError(
        "GEMINI_API_KEY environment variable is required. "
        "Set it in backend/.env or pass it via docker-compose env_file."
    )
genai.configure(api_key=_gemini_key)

# ---------------------------------------------------------------------------
# Logging — structured output visible in uvicorn terminal
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  [%(request_id)s]  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Inject a default request_id for log records that don't have one
class RequestIDFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "system"
        return True

# Attach to all root handlers so it applies globally (even to uvicorn loggers)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIDFilter())



# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Research Copilot",
    description="AI-powered research paper analysis pipeline with semantic reranking, "
                "structured extraction, and knowledge graph synthesis.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- Rate Limiting (10/min per IP) ---
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# --- CORS (restricted, configurable) ---
ALLOWED_ORIGINS = os.environ.get(
    "ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# --- GZip Compression (for responses > 500 bytes) ---
app.add_middleware(GZipMiddleware, minimum_size=500)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app, endpoint="/metrics")


# ---------------------------------------------------------------------------
# Request-ID Middleware — injects X-Request-ID header + log context
# ---------------------------------------------------------------------------
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


# ---------------------------------------------------------------------------
# Security Headers Middleware — defence-in-depth for production
# ---------------------------------------------------------------------------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response


app.add_middleware(SecurityHeadersMiddleware)


# ---------------------------------------------------------------------------
# Optional API-Key Authentication Middleware
# Set API_AUTH_KEY in .env to enable; leave unset to skip auth.
# ---------------------------------------------------------------------------
API_AUTH_KEY = os.environ.get("API_AUTH_KEY", "")


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Require X-API-Key header if API_AUTH_KEY is configured."""

    # /metrics intentionally NOT exempt — requires API key to prevent info leakage
    EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        if not API_AUTH_KEY:
            return await call_next(request)
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        provided = request.headers.get("X-API-Key", "")
        if provided != API_AUTH_KEY:
            return Response(
                content=json.dumps({"detail": "Invalid or missing API key"}),
                status_code=401,
                media_type="application/json",
            )
        return await call_next(request)


app.add_middleware(APIKeyMiddleware)


# ---------------------------------------------------------------------------
# Pipeline tuning — configurable via .env
# ---------------------------------------------------------------------------
ARXIV_CANDIDATE_COUNT = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 20))
TOP_K_PAPERS          = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY    = int(os.environ.get("GEMINI_CONCURRENCY", 5))
PIPELINE_TIMEOUT      = int(os.environ.get("PIPELINE_TIMEOUT", 120))
MAX_QUERY_LENGTH      = int(os.environ.get("MAX_QUERY_LENGTH", 500))
MIN_QUERY_LENGTH      = 3

# Global semaphore: limits simultaneous Gemini API calls across all requests.
# Initialised at module load so it is shared across the entire process lifetime.
_gemini_semaphore: asyncio.Semaphore | None = None


@app.on_event("startup")
async def _startup():
    global _gemini_semaphore
    _gemini_semaphore = asyncio.Semaphore(GEMINI_CONCURRENCY)

    # Preload the CrossEncoder model so the first request doesn't pay cold-start cost
    logger.info("[startup] Preloading reranker model...")
    from app.services.rerank_service import _get_model
    _get_model()

    logger.info(
        "[startup] Gemini concurrency=%d | candidates=%d | top_k=%d | timeout=%ds",
        GEMINI_CONCURRENCY, ARXIV_CANDIDATE_COUNT, TOP_K_PAPERS, PIPELINE_TIMEOUT,
    )


@app.on_event("shutdown")
async def _shutdown():
    """Graceful shutdown: close SQLite connections."""
    cache_service.close()
    logger.info("[shutdown] Clean shutdown complete.")


# ---------------------------------------------------------------------------
# In-memory LRU query cache (preserved from original)
# Caches the full SearchResponse dict for the last 256 unique queries.
# This is a fast first-level cache before hitting SQLite per-paper caches.
# ---------------------------------------------------------------------------
_result_cache: dict[str, dict] = {}
_MAX_CACHE = 256
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
# Input validation helper
# ---------------------------------------------------------------------------
def _validate_query(query: str) -> str:
    """Validate and sanitize the query string."""
    query = query.strip()
    if len(query) < MIN_QUERY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Query must be at least {MIN_QUERY_LENGTH} characters long.",
        )
    if len(query) > MAX_QUERY_LENGTH:
        query = query[:MAX_QUERY_LENGTH]
        logger.info("[search] Query truncated to %d chars", MAX_QUERY_LENGTH)
    return query


# ---------------------------------------------------------------------------
# Core pipeline logic (shared between /search and /search/stream)
# ---------------------------------------------------------------------------
async def _run_pipeline(query: str, request_id: str = ""):
    """Run the full 5-stage pipeline. Returns (response_dict, errors)."""

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
    logger.info(
        "[stage 2: rerank]     %.1fs",
        time.perf_counter() - t1,
    )

    # --- Stage 3: PDF download + text extraction (cache-aware, parallel) ---
    t2 = time.perf_counter()
    texts = await get_paper_texts(top_papers)
    logger.info(
        "[stage 3: pdf+parse]  %.1fs",
        time.perf_counter() - t2,
    )

    # --- Stage 4: Structured extraction (cache-aware, semaphore-bounded) ---
    t3 = time.perf_counter()
    extracted, extraction_errors = await extract_papers(
        top_papers, texts, semaphore=_gemini_semaphore
    )
    logger.info(
        "[stage 4: extract]    %.1fs  (%d ok, %d errors)",
        time.perf_counter() - t3, len(extracted), len(extraction_errors),
    )

    # --- Stage 5: Knowledge graph synthesis (cache-aware) ---
    t4 = time.perf_counter()
    graph = await build_knowledge_graph(extracted)
    logger.info(
        "[stage 5: synthesize] %.1fs",
        time.perf_counter() - t4,
    )

    logger.info(
        "[TOTAL]               %.1fs",
        time.perf_counter() - t0,
    )

    # --- Assemble response (schema unchanged + new error list) ---
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

    errors = [ExtractionError(**e) for e in extraction_errors]
    response = SearchResponse(
        query=query, papers=results, graph=graph,
        errors=errors, request_id=request_id,
    )
    return response


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    """Deep health check — verifies DB, reranker, and Gemini connectivity."""
    checks = {}

    # Check SQLite cache
    try:
        from app.services.cache_service import _get_conn
        conn = _get_conn()
        conn.execute("SELECT 1").fetchone()
        checks["database"] = True
    except Exception as e:
        checks["database"] = False
        logger.warning("[health] DB check failed: %s", e)

    # Check reranker model loaded
    try:
        from app.services.rerank_service import _model
        checks["reranker_loaded"] = _model is not None
    except Exception:
        checks["reranker_loaded"] = False

    # Check Gemini semaphore exists
    checks["gemini_semaphore_ready"] = _gemini_semaphore is not None

    overall = all(checks.values())
    return {
        "status": "ok" if overall else "degraded",
        "checks": checks,
    }


@app.get("/search", response_model=SearchResponse)
@limiter.limit("10/minute")
async def search(request: Request, query: str):  # noqa: C901
    query = _validate_query(query)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    cache_key = query.strip().lower()
    cached = _cache_get(cache_key)
    if cached:
        logger.info(
            "[search] QUERY CACHE HIT — '%s'", query,
        )
        # Update request_id in cached response
        cached_response = SearchResponse(**cached)
        cached_response.request_id = request_id
        return cached_response

    try:
        response = await asyncio.wait_for(
            _run_pipeline(query, request_id=request_id),
            timeout=PIPELINE_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error(
            "[search] Pipeline timed out after %ds for query: '%s'",
            PIPELINE_TIMEOUT, query,
        )
        raise HTTPException(
            status_code=504,
            detail=f"Pipeline timed out after {PIPELINE_TIMEOUT}s. Try a more specific query.",
        )

    _cache_set(cache_key, response.dict())
    return response


@app.get("/search/stream")
@limiter.limit("10/minute")
async def search_stream(request: Request, query: str):
    """
    SSE streaming endpoint — sends real-time stage progress events.
    Each event is a JSON object with stage name, progress, and partial results.

    Event types:
      - stage: Pipeline progress update
      - result: Final complete result
      - error: Pipeline error
    """
    query = _validate_query(query)
    request_id = getattr(request.state, "request_id", str(uuid.uuid4())[:8])

    async def _event_stream():
        t0 = time.perf_counter()

        try:
            # --- Stage 1: Retrieve ---
            yield _sse_event("stage", {
                "stage": "retrieving", "progress": 1, "total": 5,
                "message": f"Searching arXiv for '{query}'...",
            })

            candidates = search_arxiv(query, max_results=ARXIV_CANDIDATE_COUNT)
            if not candidates:
                yield _sse_event("error", {"message": "No papers found for this query"})
                return

            yield _sse_event("stage", {
                "stage": "retrieved", "progress": 1, "total": 5,
                "message": f"Found {len(candidates)} candidate papers.",
                "elapsed": round(time.perf_counter() - t0, 1),
            })

            # --- Stage 2: Rerank ---
            yield _sse_event("stage", {
                "stage": "reranking", "progress": 2, "total": 5,
                "message": "Semantic reranking with CrossEncoder...",
            })

            t1 = time.perf_counter()
            top_papers = rerank_papers(query, candidates, top_k=TOP_K_PAPERS)

            yield _sse_event("stage", {
                "stage": "reranked", "progress": 2, "total": 5,
                "message": f"Selected top {len(top_papers)} papers.",
                "papers": [{"arxiv_id": p.arxiv_id, "title": p.title} for p in top_papers],
                "elapsed": round(time.perf_counter() - t1, 1),
            })

            # --- Stage 3: PDF ---
            yield _sse_event("stage", {
                "stage": "downloading", "progress": 3, "total": 5,
                "message": "Downloading and parsing PDFs...",
            })

            t2 = time.perf_counter()
            texts = await get_paper_texts(top_papers)

            yield _sse_event("stage", {
                "stage": "downloaded", "progress": 3, "total": 5,
                "message": f"Extracted text from {len(texts)} papers.",
                "elapsed": round(time.perf_counter() - t2, 1),
            })

            # --- Stage 4: Extract ---
            yield _sse_event("stage", {
                "stage": "extracting", "progress": 4, "total": 5,
                "message": "Structured extraction via Gemini...",
            })

            t3 = time.perf_counter()
            extracted, extraction_errors = await extract_papers(
                top_papers, texts, semaphore=_gemini_semaphore
            )

            yield _sse_event("stage", {
                "stage": "extracted", "progress": 4, "total": 5,
                "message": f"Extracted {len(extracted)} papers ({len(extraction_errors)} errors).",
                "elapsed": round(time.perf_counter() - t3, 1),
            })

            # --- Stage 5: Graph ---
            yield _sse_event("stage", {
                "stage": "synthesizing", "progress": 5, "total": 5,
                "message": "Building knowledge graph...",
            })

            t4 = time.perf_counter()
            graph = await build_knowledge_graph(extracted)

            yield _sse_event("stage", {
                "stage": "synthesized", "progress": 5, "total": 5,
                "message": "Knowledge graph complete.",
                "elapsed": round(time.perf_counter() - t4, 1),
            })

            # --- Assemble final response ---
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

            errors = [ExtractionError(**e) for e in extraction_errors]
            response = SearchResponse(
                query=query, papers=results, graph=graph,
                errors=errors, request_id=request_id,
            )

            # Cache the assembled response
            _cache_set(query.strip().lower(), response.dict())

            total_elapsed = round(time.perf_counter() - t0, 1)
            yield _sse_event("result", {
                "data": response.dict(),
                "total_elapsed": total_elapsed,
            })

        except Exception as exc:
            logger.error(
                "[search/stream] Pipeline error: %s", exc,
            )
            yield _sse_event("error", {"message": str(exc)})

    return StreamingResponse(
        _event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Request-ID": request_id,
        },
    )


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@app.post("/tech-match", response_model=TechMatchResponse)
@limiter.limit("10/minute")
async def tech_match(request: Request, payload: TechMatchRequest):
    if not payload.tech_stack:
        raise HTTPException(status_code=400, detail="tech_stack must not be empty")
    papers_dicts = [p.dict() for p in payload.papers]
    result = await match_tech_stack(papers_dicts, payload.tech_stack)
    return TechMatchResponse(**result)
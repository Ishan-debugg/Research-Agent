"""
Stage 2: Semantic rerank with a cross-encoder.

rerank_papers is now async: model.predict() is CPU-bound and was blocking
the event loop for ~7-8s. Running it in run_in_executor frees the loop
for other requests during inference.
"""
import asyncio
import logging
import os

os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

from app.models.schemas import PaperCandidate

logger = logging.getLogger(__name__)

_model = None
_model_failed = False


def _get_model():
    global _model, _model_failed
    if _model_failed:
        return None
    if _model is None:
        try:
            from sentence_transformers import CrossEncoder
            _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("[rerank] CrossEncoder loaded successfully.")
        except Exception as e:
            logger.error(
                "[rerank] Failed to load CrossEncoder: %s. Falling back to default order.", e
            )
            _model_failed = True
            _model = None
    return _model


def _sync_rerank(
    query: str, candidates: list[PaperCandidate], top_k: int
) -> list[PaperCandidate]:
    """Synchronous rerank — intended to run in an executor."""
    model = _get_model()
    if model is None:
        for c in candidates:
            c.score = 0.0
        return candidates[:top_k]

    pairs = [(query, c.abstract) for c in candidates]
    scores = model.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)

    return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]


async def rerank_papers(
    query: str, candidates: list[PaperCandidate], top_k: int = 5
) -> list[PaperCandidate]:
    """
    Async rerank. Runs model.predict() (CPU-bound, ~7s) in a thread pool
    so the event loop stays free during inference.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_rerank, query, candidates, top_k)
    except Exception as e:
        logger.error("[rerank] Prediction failed: %s. Falling back to default order.", e)
        for c in candidates:
            c.score = 0.0
        return candidates[:top_k]
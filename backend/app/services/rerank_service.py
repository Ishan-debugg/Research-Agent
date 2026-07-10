"""
Stage 2: Semantic rerank with a fast bi-encoder (cosine similarity).

Replaces the previous CrossEncoder — which runs full joint cross-attention
over every (query, abstract) pair and took ~7-8s on CPU for 20 candidates —
with a SentenceTransformer bi-encoder. The query and every abstract are each
embedded independently into a shared vector space, and scoring is just a
batched cosine-similarity matrix multiply. That's what makes it fast: no
joint attention pass per pair, and all candidate abstracts are embedded in
one batched call.

rerank_papers is still async: model.encode() is CPU-bound, so it runs inside
run_in_executor to keep the event loop free during inference.
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
            from sentence_transformers import SentenceTransformer
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("[rerank] Bi-encoder (all-MiniLM-L6-v2) loaded successfully.")
        except Exception as e:
            logger.error(
                "[rerank] Failed to load bi-encoder: %s. Falling back to default order.", e
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

    from sentence_transformers import util

    # Bi-encoder: embed the query once and every abstract in a single batched
    # call, then score with cosine similarity — no per-pair cross-attention.
    query_embedding = model.encode(
        query, convert_to_tensor=True, normalize_embeddings=True,
    )
    abstract_embeddings = model.encode(
        [c.abstract for c in candidates],
        convert_to_tensor=True,
        normalize_embeddings=True,
        batch_size=32,
    )

    scores = util.cos_sim(query_embedding, abstract_embeddings)[0]

    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)

    return sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]


async def rerank_papers(
    query: str, candidates: list[PaperCandidate], top_k: int = 5
) -> list[PaperCandidate]:
    """
    Async rerank. Runs model.encode() (CPU-bound — typically well under 1s
    for ~20 candidates with a bi-encoder, versus ~7-8s for the old
    cross-encoder) in a thread pool so the event loop stays free during
    inference.
    """
    try:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _sync_rerank, query, candidates, top_k)
    except Exception as e:
        logger.error("[rerank] Prediction failed: %s. Falling back to default order.", e)
        for c in candidates:
            c.score = 0.0
        return candidates[:top_k]
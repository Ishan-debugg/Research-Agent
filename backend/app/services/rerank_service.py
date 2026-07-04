"""
Stage 2: Semantic rerank with a cross-encoder.

Why a cross-encoder instead of just cosine similarity on embeddings?
A cross-encoder reads the query and the abstract TOGETHER in one pass,
so it judges relevance more accurately than comparing two separate
embedding vectors. It's slower per-pair, but we're only scoring ~20
abstracts, so it's still fast (runs fine on CPU, no GPU needed).

Model is small (~100MB) and downloads once on first run.
"""
import logging
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
        except Exception as e:
            logger.error("[rerank] Failed to load CrossEncoder (e.g. system memory/paging file limits): %s. Falling back to default order.", e)
            _model_failed = True
            _model = None
    return _model


def rerank_papers(
    query: str, candidates: list[PaperCandidate], top_k: int = 5
) -> list[PaperCandidate]:
    """Scores each candidate's abstract against the query and returns the top_k."""
    model = _get_model()
    if model is None:
        # Fallback: set score to 0.0 and return top_k in their original order
        for c in candidates:
            c.score = 0.0
        return candidates[:top_k]

    try:
        pairs = [(query, c.abstract) for c in candidates]
        scores = model.predict(pairs)

        for candidate, score in zip(candidates, scores):
            candidate.score = float(score)

        ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
        return ranked[:top_k]
    except Exception as e:
        logger.error("[rerank] Prediction execution failed: %s. Falling back to default order.", e)
        for c in candidates:
            c.score = 0.0
        return candidates[:top_k]


if __name__ == "__main__":
    # quick manual test
    from app.services.arxiv_service import search_arxiv

    query = "retrieval-augmented generation"
    candidates = search_arxiv(query, max_results=20)
    top = rerank_papers(query, candidates, top_k=5)
    for p in top:
        print(f"{p.score:.3f}  {p.title}")
"""
Stage 2: Semantic rerank with a cross-encoder.

Why a cross-encoder instead of just cosine similarity on embeddings?
A cross-encoder reads the query and the abstract TOGETHER in one pass,
so it judges relevance more accurately than comparing two separate
embedding vectors. It's slower per-pair, but we're only scoring ~20
abstracts, so it's still fast (runs fine on CPU, no GPU needed).

Model is small (~100MB) and downloads once on first run.
"""
from sentence_transformers import CrossEncoder
from app.models.schemas import PaperCandidate

_model = None


def _get_model() -> CrossEncoder:
    global _model
    if _model is None:
        _model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    return _model


def rerank_papers(
    query: str, candidates: list[PaperCandidate], top_k: int = 5
) -> list[PaperCandidate]:
    """Scores each candidate's abstract against the query and returns the top_k."""
    model = _get_model()
    pairs = [(query, c.abstract) for c in candidates]
    scores = model.predict(pairs)

    for candidate, score in zip(candidates, scores):
        candidate.score = float(score)

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    return ranked[:top_k]


if __name__ == "__main__":
    # quick manual test
    from app.services.arxiv_service import search_arxiv

    query = "retrieval-augmented generation"
    candidates = search_arxiv(query, max_results=20)
    top = rerank_papers(query, candidates, top_k=5)
    for p in top:
        print(f"{p.score:.3f}  {p.title}")
"""
Stage 1: arXiv retrieval.

Free, no API key needed. arXiv's own guideline is to stay polite with
request frequency, so we keep this to one search call per user query
rather than looping calls.
"""
import arxiv
from app.models.schemas import PaperCandidate


def search_arxiv(query: str, max_results: int = 20) -> list[PaperCandidate]:
    """
    Pull candidate papers for a topic. Returns metadata + abstract only -
    full text comes later in the PDF stage, only for the papers that
    survive reranking (saves time and bandwidth).
    """
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )

    candidates = []
    for result in client.results(search):
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


if __name__ == "__main__":
    # quick manual test: python -m app.services.arxiv_service
    papers = search_arxiv("retrieval-augmented generation", max_results=5)
    for p in papers:
        print(f"- {p.title}  ({p.arxiv_id})")

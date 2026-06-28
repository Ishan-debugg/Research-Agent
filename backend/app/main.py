"""
Main FastAPI app. Wires stages 1-5 into a single /search endpoint.
Merges Gemini's extraction with arXiv's own metadata (authors/year)
before returning, since that metadata is more reliable from the source.
"""
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.models.schemas import SearchResponse, PaperResult
from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph

load_dotenv()

app = FastAPI(title="Research Copilot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ARXIV_CANDIDATE_COUNT = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 20))
TOP_K_PAPERS = int(os.environ.get("TOP_K_PAPERS", 5))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/search", response_model=SearchResponse)
async def search(query: str):
    if not query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    candidates = search_arxiv(query, max_results=ARXIV_CANDIDATE_COUNT)
    if not candidates:
        raise HTTPException(status_code=404, detail="No papers found for this query")

    top_papers = rerank_papers(query, candidates, top_k=TOP_K_PAPERS)
    texts = await get_paper_texts(top_papers)
    extracted = extract_papers(top_papers, texts)
    graph = build_knowledge_graph(extracted)

    # Merge Gemini's extraction with arXiv's own metadata, keyed by arxiv_id
    candidates_by_id = {p.arxiv_id: p for p in top_papers}
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
                problem=e.problem,
                method=e.method,
                dataset=e.dataset,
                results=e.results,
                contribution=e.contribution,
                precision=e.precision,
                recall=e.recall,
                f1_score=e.f1_score,
                accuracy=e.accuracy,
                auc=e.auc,
                other_metrics=e.other_metrics,
            )
        )

    return SearchResponse(query=query, papers=results, graph=graph)
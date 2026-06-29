"""
Main FastAPI app. /search runs the full pipeline; /tech-match is a
separate, optional, on-demand call.
"""
import os
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
                eval_method=e.eval_method,
                results=e.results,
                contribution=e.contribution,
                limitations=e.limitations,
                prerequisites=e.prerequisites,
                real_world_impact=e.real_world_impact,
                precision=e.precision,
                recall=e.recall,
                f1_score=e.f1_score,
                accuracy=e.accuracy,
                auc=e.auc,
                bleu=e.bleu,
                rouge=e.rouge,
                other_metrics=e.other_metrics,
            )
        )

    return SearchResponse(query=query, papers=results, graph=graph)


@app.post("/tech-match", response_model=TechMatchResponse)
def tech_match(payload: TechMatchRequest):
    if not payload.tech_stack:
        raise HTTPException(status_code=400, detail="tech_stack must not be empty")
    papers_dicts = [p.dict() for p in payload.papers]
    result = match_tech_stack(papers_dicts, payload.tech_stack)
    return TechMatchResponse(**result)
    
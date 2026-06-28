"""
Pydantic models shared across the pipeline.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class PaperCandidate(BaseModel):
    """A paper as it comes back from arXiv, before reranking."""
    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    published: str
    pdf_url: str
    score: Optional[float] = None


class ExtractedPaper(BaseModel):
    """Structured fields pulled out of a paper's full text by Gemini."""
    arxiv_id: str
    title: str
    problem: str
    method: str
    dataset: str
    results: str
    contribution: str
    # Benchmark metrics - "Not reported" if the paper's text doesn't state them.
    # Never guessed/estimated by the model; only pulled when explicitly present.
    precision: str = "Not reported"
    recall: str = "Not reported"
    f1_score: str = "Not reported"
    accuracy: str = "Not reported"
    auc: str = "Not reported"
    other_metrics: str = "Not reported"


class PaperResult(BaseModel):
    """
    Final per-paper shape returned to the frontend: Gemini's extraction
    merged with arXiv's own metadata (authors/year/pdf link), since the
    metadata is more reliable coming straight from arXiv than re-asking
    the LLM to recall it.
    """
    arxiv_id: str
    title: str
    authors: List[str]
    year: str
    pdf_url: str
    problem: str
    method: str
    dataset: str
    results: str
    contribution: str
    precision: str = "Not reported"
    recall: str = "Not reported"
    f1_score: str = "Not reported"
    accuracy: str = "Not reported"
    auc: str = "Not reported"
    other_metrics: str = "Not reported"


class GraphNode(BaseModel):
    id: str
    label: str
    type: str = "paper"


class GraphEdge(BaseModel):
    source: str
    target: str
    relationship: str


class KnowledgeGraph(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    open_problems: List[str] = Field(default_factory=list)
    summary: str = ""


class SearchResponse(BaseModel):
    query: str
    papers: List[PaperResult]
    graph: KnowledgeGraph
    
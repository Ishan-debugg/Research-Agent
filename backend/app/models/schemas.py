"""
Pydantic models shared across the pipeline.
"""
from pydantic import BaseModel, Field
from typing import List, Dict


class PaperCandidate(BaseModel):
    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    published: str
    pdf_url: str
    score: float = None


class ExtractedPaper(BaseModel):
    arxiv_id: str
    title: str
    problem: str
    method: str
    dataset: str
    eval_method: str = "Not specified"
    results: str
    contribution: str
    limitations: str = "Not specified"
    prerequisites: str = "None specified"
    real_world_impact: str = ""
    audience: str = "General ML researchers"
    precision: str = "Not reported"
    recall: str = "Not reported"
    f1_score: str = "Not reported"
    accuracy: str = "Not reported"
    auc: str = "Not reported"
    bleu: str = "Not reported"
    rouge: str = "Not reported"
    other_metrics: str = "Not reported"
    baseline: str = "Not reported"


class PaperResult(BaseModel):
    arxiv_id: str
    title: str
    authors: List[str]
    year: str
    pdf_url: str
    relevance_score: int = 0
    problem: str
    method: str
    dataset: str
    eval_method: str = "Not specified"
    results: str
    contribution: str
    limitations: str = "Not specified"
    prerequisites: str = "None specified"
    real_world_impact: str = ""
    audience: str = "General ML researchers"
    precision: str = "Not reported"
    recall: str = "Not reported"
    f1_score: str = "Not reported"
    accuracy: str = "Not reported"
    auc: str = "Not reported"
    bleu: str = "Not reported"
    rouge: str = "Not reported"
    other_metrics: str = "Not reported"
    baseline: str = "Not reported"


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


class TechMatchPaperInput(BaseModel):
    arxiv_id: str
    title: str
    method: str = ""
    contribution: str = ""


class TechMatchRequest(BaseModel):
    tech_stack: List[str]
    papers: List[TechMatchPaperInput]


class TechMatchItem(BaseModel):
    tech: str
    level: str
    explanation: str


class TechMatchResponse(BaseModel):
    matches: Dict[str, List[TechMatchItem]]

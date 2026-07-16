"""
Pydantic models shared across the pipeline.

Changes:
  - SearchResponse now includes optional 'errors' and 'request_id' fields.
  - 'errors' carries details about papers that failed extraction (graceful degradation).
  - 'request_id' is a UUID assigned by the middleware for traceability.
"""
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Optional, Any


class PaperCandidate(BaseModel):
    arxiv_id: str
    title: str
    abstract: str
    authors: List[str]
    published: str
    pdf_url: str
    score: float = None


def _coerce_str(v: Any) -> str:
    """Coerce any non-string value to a readable string.
    
    LLMs occasionally return dicts or lists for text fields (e.g. results,
    method). Without coercion pydantic raises a validation error and the
    entire paper is silently dropped. This validator makes every string field
    fault-tolerant.
    """
    if v is None:
        return "Not reported"
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        # Convert {'metric': 'value', ...} to a readable string
        return "; ".join(f"{k}: {v2}" for k, v2 in v.items())
    if isinstance(v, list):
        return "; ".join(str(x) for x in v)
    return str(v)


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

    # Coerce all text fields — prevents pydantic ValidationError when LLM
    # returns a nested dict/list instead of a plain string.
    @field_validator(
        "problem", "method", "dataset", "eval_method", "results", "contribution",
        "limitations", "prerequisites", "real_world_impact", "audience",
        "precision", "recall", "f1_score", "accuracy", "auc",
        "bleu", "rouge", "other_metrics", "baseline",
        mode="before",
    )
    @classmethod
    def coerce_to_str(cls, v: Any) -> str:
        return _coerce_str(v)


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


class ExtractionError(BaseModel):
    """Details about a paper that failed during extraction."""
    arxiv_id: str
    title: str = "Unknown"
    error: str


class SearchResponse(BaseModel):
    query: str
    papers: List[PaperResult]
    graph: KnowledgeGraph
    errors: List[ExtractionError] = Field(default_factory=list)
    request_id: Optional[str] = None


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

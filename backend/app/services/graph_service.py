"""
Stage 5: Knowledge graph synthesis.

Second (and last) Gemini call per search. Takes the structured extractions
from stage 4 and asks the model to relate them: clusters, dependencies,
shared datasets, contradictions, and open problems across the set.
"""
import json
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from app.models.schemas import ExtractedPaper, KnowledgeGraph
from app.services.extraction_service import MODEL_NAME

GRAPH_PROMPT = """You are synthesizing a research landscape from {count} extracted paper summaries.

Identify relationships between papers (e.g. "builds_on", "contradicts", "shares_dataset",
"alternative_approach") and any open problems the set collectively suggests.

Respond ONLY with JSON, no markdown fences, matching this exact shape:
{{
  "nodes": [{{"id": "<arxiv_id>", "label": "<short title>", "type": "paper"}}, ...],
  "edges": [{{"source": "<arxiv_id>", "target": "<arxiv_id>", "relationship": "<short label>"}}, ...],
  "open_problems": ["<short phrase>", ...],
  "summary": "<2-3 sentence overview of the landscape>"
}}

PAPER SUMMARIES:
{summaries_block}
"""


def _build_summaries_block(papers: list[ExtractedPaper]) -> str:
    blocks = []
    for p in papers:
        blocks.append(
            f"---\narxiv_id: {p.arxiv_id}\ntitle: {p.title}\n"
            f"problem: {p.problem}\nmethod: {p.method}\n"
            f"results: {p.results}\ncontribution: {p.contribution}\n"
        )
    return "\n".join(blocks)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_gemini(prompt: str) -> str:
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    return response.text


def build_knowledge_graph(papers: list[ExtractedPaper]) -> KnowledgeGraph:
    prompt = GRAPH_PROMPT.format(
        count=len(papers), summaries_block=_build_summaries_block(papers)
    )
    raw = _call_gemini(prompt)
    data = json.loads(raw)
    return KnowledgeGraph(**data)

    
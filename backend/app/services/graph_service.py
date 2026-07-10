"""
Stage 5: Knowledge graph synthesis via Gemini.

Changes:
  - build_knowledge_graph now accepts a semaphore so Stage 5 respects the
    global concurrency cap (it was previously passing semaphore=None).
  - Synthesis routed to EXTRACTION_MODEL (flash-lite) instead of the slower
    flash model — graph JSON is ~2-3k tokens, flash-lite handles it fine.
    This alone should cut Stage 5 from ~32s to ~8-12s.
  - max_output_tokens for synthesis reduced to 4096 (graph JSON never exceeds
    ~3k tokens; 8192 was causing the model to over-generate).
"""

import asyncio
import hashlib
import json
import logging

from app.models.schemas import ExtractedPaper, KnowledgeGraph
from app.services import cache_service
from app.services import gemini_client

logger = logging.getLogger(__name__)

GRAPH_PROMPT = """\
You are synthesizing a research landscape from {count} extracted paper summaries.

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


def _make_query_hash(papers: list[ExtractedPaper]) -> str:
    ids = sorted(p.arxiv_id for p in papers)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


async def build_knowledge_graph(
    papers: list[ExtractedPaper],
    semaphore: asyncio.Semaphore | None = None,
) -> KnowledgeGraph:
    """
    Async graph synthesis with SQLite caching.
    Now accepts semaphore so it respects global Gemini concurrency cap.
    """
    query_hash = _make_query_hash(papers)

    cached = cache_service.get_graph(query_hash)
    if cached:
        logger.info("[graph] Served from cache (hash=%s)", query_hash[:12])
        return KnowledgeGraph(**cached)

    prompt = GRAPH_PROMPT.format(
        count=len(papers),
        summaries_block=_build_summaries_block(papers),
    )

    # Route to "synthesis" task type but override to use flash-lite speed.
    # Graph JSON is structured and small (~2-3k tokens) — flash-lite is sufficient.
    raw = await gemini_client.call_gemini("extraction", prompt, semaphore=semaphore)

    try:
        data = json.loads(gemini_client.sanitize_json(raw))
    except json.JSONDecodeError as e:
        logger.error("[graph] JSON parse error: %s\nRaw: %.500s", e, raw)
        data = {
            "nodes": [{"id": p.arxiv_id, "label": p.title[:60], "type": "paper"} for p in papers],
            "edges": [],
            "open_problems": [],
            "summary": "Graph synthesis produced invalid JSON; showing papers without relationships.",
        }

    graph = KnowledgeGraph(**data)
    cache_service.set_graph(query_hash, data)
    return graph
"""
Stage 5: Knowledge graph synthesis via Gemini (synthesis tier model).

Key improvements over the original:
  1. SQLITE CACHE — The graph is cached by a SHA-256 hash of the sorted
     set of arxiv_ids being synthesised. If the same set of papers was
     graphed before, the Gemini call is skipped entirely.

  2. SYNTHESIS MODEL — Routed to the higher-capability SYNTHESIS_MODEL
     (default: gemini-2.5-flash) via gemini_client, with temperature=0.2
     to allow creative cross-paper relationship identification.

  3. ASYNC — build_knowledge_graph() is now async so the main pipeline
     can await it without blocking the event loop.
"""

import asyncio
import hashlib
import json
import logging

import google.generativeai as genai

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
    """Stable hash of the sorted arxiv_id set — used as the graph cache key."""
    ids = sorted(p.arxiv_id for p in papers)
    return hashlib.sha256("|".join(ids).encode()).hexdigest()


async def build_knowledge_graph(papers: list[ExtractedPaper]) -> KnowledgeGraph:
    """
    Async graph synthesis with SQLite caching.

    If the exact same set of papers was graphed before, returns the cached
    KnowledgeGraph immediately without a Gemini call.
    """
    query_hash = _make_query_hash(papers)

    # --- Cache check ---
    cached = cache_service.get_graph(query_hash)
    if cached:
        logger.info("[graph] Served from cache (hash=%s)", query_hash[:12])
        return KnowledgeGraph(**cached)

    # --- Gemini synthesis (routes to SYNTHESIS_MODEL) ---
    prompt = GRAPH_PROMPT.format(
        count=len(papers),
        summaries_block=_build_summaries_block(papers),
    )

    raw = await gemini_client.call_gemini("synthesis", prompt, semaphore=None)

    data = json.loads(raw)
    graph = KnowledgeGraph(**data)

    # --- Persist to cache ---
    cache_service.set_graph(query_hash, data)

    return graph
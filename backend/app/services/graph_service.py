"""
Stage 5: Knowledge graph synthesis.

Primary:  Groq llama-3.3-70b-versatile  — fast (~2-4s), reliable, no daily quota.
Fallback: Gemini SYNTHESIS_MODEL        — higher quality, used if Groq fails.

Why Groq for graphs?
  - The graph prompt is small (~1,200 tokens for 5 papers) — comfortably under
    Groq's free-tier 6K TPM limit, unlike the extraction batch prompt.
  - llama-3.3-70b-versatile has strong enough reasoning to identify inter-paper
    relationships, open problems, and write coherent summaries.
  - Eliminates the Gemini daily-quota exhaustion problem that caused 30s+ waits.

Why keep Gemini as fallback?
  - If Groq is unavailable or rate-limited, Gemini 2.0-flash still works.
  - Ensures the pipeline never silently fails on graph synthesis.
"""

import asyncio
import hashlib
import json
import logging
import os

from app.models.schemas import ExtractedPaper, KnowledgeGraph
from app.services import cache_service
from app.services import gemini_client
from app.services import groq_client

logger = logging.getLogger(__name__)

# Model used for Groq graph synthesis — configurable via GRAPH_MODEL env var.
# Mixtral is decommissioned on Groq; llama-3.3-70b-versatile is the best
# available reasoning model on the free tier.
GRAPH_MODEL = os.environ.get("GRAPH_MODEL", "llama-3.3-70b-versatile")

GRAPH_SYSTEM_MESSAGE = (
    "You are a research synthesis expert. Analyze sets of ML research papers "
    "and identify relationships, themes, and open problems. "
    "Always respond with valid JSON only — no markdown fences, no preamble."
)

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


def _parse_graph_json(raw: str, papers: list[ExtractedPaper]) -> dict:
    """Parse raw JSON string into a graph dict, with a safe fallback."""
    try:
        return json.loads(gemini_client.sanitize_json(raw))
    except json.JSONDecodeError as e:
        logger.error("[graph] JSON parse error: %s\nRaw: %.500s", e, raw)
        return {
            "nodes": [{"id": p.arxiv_id, "label": p.title[:60], "type": "paper"} for p in papers],
            "edges": [],
            "open_problems": [],
            "summary": "Graph synthesis produced invalid JSON; showing papers without relationships.",
        }


async def build_knowledge_graph(
    papers: list[ExtractedPaper],
    semaphore: asyncio.Semaphore | None = None,
) -> KnowledgeGraph:
    """
    Async graph synthesis with SQLite caching.

    Strategy:
      1. Cache hit  → instant (0 API calls).
      2. Groq primary (llama-3.3-70b-versatile) → ~2-4s, reliable.
      3. Gemini fallback (SYNTHESIS_MODEL)       → if Groq fails.
    """
    if not papers:
        logger.warning("[graph] build_knowledge_graph called with 0 papers — returning empty graph.")
        return KnowledgeGraph(
            nodes=[],
            edges=[],
            open_problems=["No papers were successfully extracted. Check extraction errors above."],
            summary="Graph synthesis requires at least one successfully extracted paper.",
        )

    query_hash = _make_query_hash(papers)

    cached = cache_service.get_graph(query_hash)
    if cached:
        logger.info("[graph] Served from cache (hash=%s)", query_hash[:12])
        return KnowledgeGraph(**cached)

    prompt = GRAPH_PROMPT.format(
        count=len(papers),
        summaries_block=_build_summaries_block(papers),
    )

    # ── Primary: Groq llama-3.3-70b-versatile ────────────────────────────────
    raw = None
    try:
        raw = await groq_client.call_groq(
            prompt,
            semaphore=semaphore,
            system_message=GRAPH_SYSTEM_MESSAGE,
            model_override=GRAPH_MODEL,
        )
        logger.info("[graph] Groq synthesis complete (model=%s)", GRAPH_MODEL)
    except Exception as groq_exc:
        logger.warning(
            "[graph] Groq failed (%s) — falling back to Gemini %s",
            groq_exc, gemini_client.SYNTHESIS_MODEL,
        )

    # ── Fallback: Gemini synthesis model ─────────────────────────────────────
    if raw is None:
        try:
            raw = await gemini_client.call_gemini("synthesis", prompt, semaphore=semaphore)
            logger.info("[graph] Gemini fallback synthesis complete")
        except Exception as gemini_exc:
            logger.error("[graph] Both Groq and Gemini failed: %s", gemini_exc)
            # Return a minimal valid graph so the pipeline doesn't crash
            data = {
                "nodes": [{"id": p.arxiv_id, "label": p.title[:60], "type": "paper"} for p in papers],
                "edges": [],
                "open_problems": ["Graph synthesis unavailable — both Groq and Gemini failed."],
                "summary": "Graph synthesis could not be completed due to API errors.",
            }
            return KnowledgeGraph(**data)

    data = _parse_graph_json(raw, papers)
    graph = KnowledgeGraph(**data)
    cache_service.set_graph(query_hash, data)
    return graph

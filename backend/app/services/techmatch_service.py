"""
On-demand tech-stack matching. Deliberately kept OUT of the main pipeline
so it only costs a Gemini call when a user has set a tech stack in
Settings and actually views Results — not on every single search.

Updated to be a proper async function routed through gemini_client,
eliminating the fragile asyncio.get_event_loop().run_until_complete()
anti-pattern that breaks under FastAPI's async worker model.
"""
import json
import logging

from app.services import gemini_client
from app.services import groq_client

logger = logging.getLogger(__name__)

TECH_MATCH_PROMPT = """\
You are assessing how relevant {count} research papers are to a person's technical skill set.

PERSON'S TECH STACK: {tech_stack}

For EACH paper, and for EACH technology in the tech stack, judge how relevant that technology
is to actually understanding or reproducing the paper, based on its method and contribution below.
Use exactly one of: "high", "moderate", "low".
- "high": the technology is central to the paper's implementation or directly used
- "moderate": background knowledge of it helps but isn't core to the paper
- "low": largely unrelated to this paper's approach

For each, give a short explanation under 15 words (e.g. "used extensively in implementation").

Respond ONLY with JSON, no markdown fences, in this exact shape:
{{
  "matches": {{
    "<arxiv_id>": [
      {{"tech": "<technology name>", "level": "high", "explanation": "<short reason>"}}
    ]
  }}
}}

PAPERS:
{papers_block}
"""


def _build_papers_block(papers):
    blocks = []
    for p in papers:
        blocks.append(
            "---\narxiv_id: " + p["arxiv_id"] + "\ntitle: " + p["title"]
            + "\nmethod: " + p.get("method", "") + "\ncontribution: " + p.get("contribution", "") + "\n"
        )
    return "\n".join(blocks)


async def match_tech_stack(papers, tech_stack):
    """
    Async tech-stack matching. Previously used the fragile
    asyncio.get_event_loop().run_until_complete() pattern — now a proper
    async function so FastAPI can await it directly without thread-pool hacks.
    """
    prompt = TECH_MATCH_PROMPT.format(
        count=len(papers),
        tech_stack=", ".join(tech_stack),
        papers_block=_build_papers_block(papers),
    )
    TECH_SYSTEM = (
        "You are a research relevance expert. Assess how relevant ML papers are "
        "to a given tech stack. Always respond with valid JSON only — "
        "no markdown fences, no preamble."
    )
    raw = await groq_client.call_groq(
        prompt,
        semaphore=None,
        system_message=TECH_SYSTEM,
    )
    try:
        data = json.loads(gemini_client.sanitize_json(raw))
    except json.JSONDecodeError as e:
        logger.error("[techmatch] JSON parse error: %s\nRaw: %.500s", e, raw)
        return {"matches": {}}

    # Sanitize and validate data structure to avoid Pydantic validation errors
    sanitized_matches = {}
    if isinstance(data, dict) and "matches" in data and isinstance(data["matches"], dict):
        for arxiv_id, items in data["matches"].items():
            if not isinstance(items, list):
                continue
            cleaned_items = []
            for item in items:
                if isinstance(item, dict):
                    # Ensure all required keys exist and are strings
                    tech = str(item.get("tech", "Unknown"))
                    level = str(item.get("level", "low")).lower()
                    if level not in {"high", "moderate", "low"}:
                        level = "low"
                    explanation = str(item.get("explanation", "Not specified"))
                    cleaned_items.append({
                        "tech": tech,
                        "level": level,
                        "explanation": explanation
                    })
                elif isinstance(item, str):
                    # Fallback for when Gemini just returns a string (e.g. RNN)
                    cleaned_items.append({
                        "tech": item,
                        "level": "low",
                        "explanation": "Not specified"
                    })
            if cleaned_items:
                sanitized_matches[str(arxiv_id)] = cleaned_items
    
    return {"matches": sanitized_matches}
"""
On-demand tech-stack matching. Deliberately kept OUT of the main pipeline
so it only costs a Gemini call when a user has set a tech stack in
Settings and actually views Results — not on every single search.

Updated to use gemini_client for consistent model routing and fallback.
"""
import json
import logging

from app.services import gemini_client

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


def match_tech_stack(papers, tech_stack):
    import asyncio
    prompt = TECH_MATCH_PROMPT.format(
        count=len(papers),
        tech_stack=", ".join(tech_stack),
        papers_block=_build_papers_block(papers),
    )
    # Run the async gemini_client call in a new event loop slice
    raw = asyncio.get_event_loop().run_until_complete(
        gemini_client.call_gemini("extraction", prompt, semaphore=None)
    )
    return json.loads(raw)
"""
On-demand tech-stack matching. Deliberately kept OUT of the main pipeline
so it only costs a Gemini call when a user has set a tech stack in
Settings and actually views Results - not on every single search.
"""
import json
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from app.services.extraction_service import MODEL_NAME

TECH_MATCH_PROMPT = """You are assessing how relevant {count} research papers are to a person's technical skill set.

PERSON'S TECH STACK: {tech_stack}

For EACH paper, and for EACH technology in the tech stack, judge how relevant that technology is to actually understanding or reproducing the paper, based on its method and contribution below. Use exactly one of: "high", "moderate", "low".
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


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_gemini(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    return response.text


def match_tech_stack(papers, tech_stack):
    prompt = TECH_MATCH_PROMPT.format(
        count=len(papers),
        tech_stack=", ".join(tech_stack),
        papers_block=_build_papers_block(papers),
    )
    raw = _call_gemini(prompt)
    return json.loads(raw)
    
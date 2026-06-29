"""
Stage 4: Structured extraction via Gemini 3.1 Flash-Lite.
One batched call for all papers. Now also extracts audience and
baseline comparison alongside the existing fields.
"""
import os
import json
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
from app.models.schemas import ExtractedPaper

load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

EXTRACTION_PROMPT = """You are extracting structured information from machine learning research papers.

You will be given {count} papers, each with an arxiv_id and its text. For EACH paper, extract:

- problem: what problem the paper addresses (1-2 sentences)
- method: the core technical approach (1-2 sentences)
- dataset: dataset name(s) and size if stated (e.g. "SQuAD, ~100k QA pairs"), or "Not specified"
- eval_method: how the paper evaluates its approach - "zero-shot", "few-shot", "fine-tuned", "cross-validation", or a short description. Use "Not specified" if unclear.
- results: 1-2 sentence narrative summary of the key findings
- contribution: what is novel versus prior work (1-2 sentences)
- limitations: key weaknesses, stated or reasonably inferred (1-2 sentences). Always fill in - use "Not explicitly discussed" if nothing is evident.
- prerequisites: background knowledge or dependencies needed to understand the paper. Use "None specified" if self-contained.
- real_world_impact: ONE short sentence on the practical, real-world significance of this paper.
- audience: who this paper is primarily written for, as one short phrase (e.g. "NLP researchers building production RAG systems").

Benchmark metrics - extract ONLY if the paper's text explicitly states the number. NEVER estimate. Use "Not reported" if absent:
- precision
- recall
- f1_score
- accuracy
- auc
- bleu
- rouge
- other_metrics: any other reported metric not covered above, or "Not reported"
- baseline: the name of the baseline model/method the headline result was compared against (e.g. "BM25 keyword search"), or "Not reported"

Respond ONLY with a JSON array, no markdown fences, no preamble. Each element must have exactly these keys:
arxiv_id, title, problem, method, dataset, eval_method, results, contribution, limitations, prerequisites, real_world_impact, audience, precision, recall, f1_score, accuracy, auc, bleu, rouge, other_metrics, baseline

PAPERS:
{papers_block}
"""


def _build_papers_block(papers, texts):
    blocks = []
    for p in papers:
        text = texts.get(p.arxiv_id, p.abstract)
        truncated = text[:8000]
        blocks.append(
            "---\narxiv_id: " + p.arxiv_id + "\ntitle: " + p.title + "\ntext:\n" + truncated + "\n"
        )
    return "\n".join(blocks)


@retry(stop=stop_after_attempt(4), wait=wait_exponential(multiplier=2, min=2, max=30))
def _call_gemini(prompt):
    model = genai.GenerativeModel(MODEL_NAME)
    response = model.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
        request_options={"timeout": 60},
    )
    return response.text


def extract_papers(papers, texts):
    prompt = EXTRACTION_PROMPT.format(
        count=len(papers), papers_block=_build_papers_block(papers, texts)
    )
    raw = _call_gemini(prompt)
    data = json.loads(raw)
    return [ExtractedPaper(**item) for item in data]
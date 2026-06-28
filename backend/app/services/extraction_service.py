"""
Stage 4: Structured extraction via Gemini 3.1 Flash-Lite.

Still ONE batched call for all papers (not one call per paper) to protect
the free-tier rate limit. Now also extracts benchmark metrics where the
paper explicitly reports them.
"""
import os
import json
import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from dotenv import load_dotenv
from app.models.schemas import ExtractedPaper, PaperCandidate

load_dotenv()

genai.configure(api_key=os.environ["GEMINI_API_KEY"])
MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

EXTRACTION_PROMPT = """You are extracting structured information from machine learning research papers.

You will be given {count} papers, each with an arxiv_id and its text. For EACH paper, extract:
- problem: what problem the paper addresses (1-2 sentences)
- method: the core technical approach (1-2 sentences)
- dataset: what data/benchmarks were used (short, or "not specified")
- results: key quantitative or qualitative findings (1-2 sentences)
- contribution: what's novel vs prior work (1-2 sentences)
- precision: the paper's reported precision score, EXACTLY as stated (e.g. "92.3%"). If not explicitly reported, use "Not reported". Never estimate.
- recall: same rule as precision, for recall.
- f1_score: same rule, for F1 score.
- accuracy: same rule, for accuracy.
- auc: same rule, for AUC/AUROC.
- other_metrics: any other reported metrics (BLEU, ROUGE, exact match, etc.) as a short string, or "Not reported".

Respond ONLY with a JSON array, no markdown fences, no preamble. Each element must have exactly these keys:
arxiv_id, title, problem, method, dataset, results, contribution, precision, recall, f1_score, accuracy, auc, other_metrics

PAPERS:
{papers_block}
"""


def _build_papers_block(papers: list[PaperCandidate], texts: dict[str, str]) -> str:
    blocks = []
    for p in papers:
        text = texts.get(p.arxiv_id, p.abstract)
        truncated = text[:8000]
        blocks.append(
            f"---\narxiv_id: {p.arxiv_id}\ntitle: {p.title}\ntext:\n{truncated}\n"
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


def extract_papers(
    papers: list[PaperCandidate], texts: dict[str, str]
) -> list[ExtractedPaper]:
    prompt = EXTRACTION_PROMPT.format(
        count=len(papers), papers_block=_build_papers_block(papers, texts)
    )
    raw = _call_gemini(prompt)
    data = json.loads(raw)
    return [ExtractedPaper(**item) for item in data]


if __name__ == "__main__":
    import asyncio
    from app.services.arxiv_service import search_arxiv
    from app.services.rerank_service import rerank_papers
    from app.services.pdf_service import get_paper_texts

    async def main():
        query = "retrieval-augmented generation"
        candidates = search_arxiv(query, max_results=20)
        top = rerank_papers(query, candidates, top_k=5)
        texts = await get_paper_texts(top)
        extracted = extract_papers(top, texts)
        for e in extracted:
            print(f"\n{e.title}\n  F1: {e.f1_score}  Accuracy: {e.accuracy}")

    asyncio.run(main())
    
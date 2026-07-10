"""
4-search timing benchmark — tests cold vs warm (cache) paths.
Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_4searches.py
"""
import asyncio
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
_key = os.environ.get("GEMINI_API_KEY")
if not _key:
    sys.exit("ERROR: GEMINI_API_KEY not set.")
genai.configure(api_key=_key)

from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers, _get_model
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph
from app.services import cache_service

ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 5))

QUERIES = [
    "BERT language model fine-tuning NLP tasks",
    "graph neural networks molecular property prediction",
    "diffusion models image generation stable diffusion",
    "federated learning privacy preserving machine learning",
]


async def run_one(query: str, sem: asyncio.Semaphore) -> dict:
    """Run the full pipeline for one query and return per-stage timings."""
    wall = time.perf_counter()
    timings = {}

    # Stage 1
    t = time.perf_counter()
    candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
    timings["arxiv"] = round(time.perf_counter() - t, 2)
    if not candidates:
        return {"error": "No papers found", "total": round(time.perf_counter() - wall, 2)}

    # Stage 2
    t = time.perf_counter()
    top = await rerank_papers(query, candidates, top_k=TOP_K)
    timings["rerank"] = round(time.perf_counter() - t, 2)

    # Stage 3
    t = time.perf_counter()
    texts = await get_paper_texts(top)
    timings["text"] = round(time.perf_counter() - t, 2)

    # Stage 4
    t = time.perf_counter()
    extracted, errors = await extract_papers(top, texts, semaphore=sem)
    timings["extract"] = round(time.perf_counter() - t, 2)
    timings["extract_errors"] = len(errors)

    # Stage 5
    t = time.perf_counter()
    graph = await build_knowledge_graph(extracted, semaphore=sem)
    timings["graph"] = round(time.perf_counter() - t, 2)

    timings["total"] = round(time.perf_counter() - wall, 2)
    timings["papers"] = len(extracted)
    timings["nodes"] = len(graph.nodes)
    return timings


def bar(val, total, width=20):
    filled = max(1, int(val / max(total, 0.01) * width))
    return "█" * filled + "░" * (width - filled)


async def run():
    sem = asyncio.Semaphore(GEMINI_CONCURRENCY)
    _get_model()  # preload reranker

    print("\n" + "=" * 70)
    print("  4-QUERY PIPELINE BENCHMARK")
    print(f"  candidates={ARXIV_CANDIDATES}  top_k={TOP_K}  ENRICH_WITH_PDF={os.environ.get('ENRICH_WITH_PDF','false')}")
    print("=" * 70)

    all_results = []

    for i, query in enumerate(QUERIES, 1):
        print(f"\n[{i}/4] Query: \"{query}\"")
        print("       Running pipeline...")
        result = await run_one(query, sem)

        if "error" in result:
            print(f"       ERROR: {result['error']}")
            all_results.append(result)
            continue

        total = result["total"]
        target_ok = total <= 30.0
        icon = "✅" if target_ok else "⚠️ "

        print(f"       {icon} TOTAL: {total:.2f}s  ({result['papers']} papers, {result['nodes']} graph nodes)")
        print(f"       ┌─ arXiv   {result['arxiv']:5.2f}s  {bar(result['arxiv'], total)}")
        print(f"       ├─ Rerank  {result['rerank']:5.2f}s  {bar(result['rerank'], total)}")
        print(f"       ├─ Text    {result['text']:5.2f}s  {bar(result['text'], total)}")
        print(f"       ├─ Extract {result['extract']:5.2f}s  {bar(result['extract'], total)}  ({result['extract_errors']} errors)")
        print(f"       └─ Graph   {result['graph']:5.2f}s  {bar(result['graph'], total)}")
        all_results.append(result)

    # Summary table
    valid = [r for r in all_results if "total" in r and "error" not in r]
    if valid:
        totals = [r["total"] for r in valid]
        print("\n" + "=" * 70)
        print("  SUMMARY")
        print("=" * 70)
        print(f"  Queries tested : {len(QUERIES)}")
        print(f"  Avg total      : {sum(totals)/len(totals):.2f}s")
        print(f"  Min total      : {min(totals):.2f}s")
        print(f"  Max total      : {max(totals):.2f}s")
        passed = sum(1 for t in totals if t <= 30)
        print(f"  ≤30s target    : {passed}/{len(valid)} passed")

        # Per-stage averages
        print(f"\n  Stage averages:")
        for stage in ("arxiv", "rerank", "text", "extract", "graph"):
            avg = sum(r.get(stage, 0) for r in valid) / len(valid)
            print(f"    {stage:<10} {avg:.2f}s avg")

if __name__ == "__main__":
    asyncio.run(run())

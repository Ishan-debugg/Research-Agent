"""
Search-only Benchmark: Measures response time for the 3 reliable pipeline stages
(arXiv Search → Semantic Rerank → PDF/Abstract Fetch) across 5 different queries.
Skips Gemini API calls (Stages 4 & 5) to avoid rate-limit issues.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_search_timing.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers, _get_model
from app.services.pdf_service import get_paper_texts

ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K = int(os.environ.get("TOP_K_PAPERS", 5))

QUERIES = [
    "Unsupervised Learning",
    "BART language model",
    "LoRA low-rank adaptation",
    "QLoRA quantized low-rank adaptation",
    "Random Forest classification",
]

STAGE_NAMES = ["arXiv Search", "Semantic Rerank", "PDF/Abstract Fetch"]

# ─── pretty helpers ───────────────────────────────────────────────────────────
SEP   = "─" * 72
DSEP  = "═" * 72

def hdr(text):
    print(f"\n{DSEP}")
    print(f"  {text}")
    print(DSEP)

def row(label, value, indent=2):
    pad = " " * indent
    print(f"{pad}  {label:<34} {value}")

def progress_bar(value, total, width=28):
    pct = value / total if total else 0
    filled = max(1, int(pct * width))
    return "█" * filled + "░" * (width - filled), pct * 100

# ─── single query run ─────────────────────────────────────────────────────────
async def benchmark_query(query: str, idx: int) -> dict:
    print(f"\n  [{idx}/5]  Query: \"{query}\"")
    print(f"         Started: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
    print(f"  {SEP}")

    stages = {}
    wall = time.perf_counter()

    # Stage 1 – arXiv
    t0 = time.perf_counter()
    candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
    s1 = time.perf_counter() - t0
    stages["arXiv Search"] = s1
    print(f"    Stage 1 | arXiv Search        {s1:6.2f}s  →  {len(candidates)} papers found")

    if not candidates:
        total = time.perf_counter() - wall
        print(f"    [!] No arXiv results — stopping early")
        return {"query": query, "stages": stages, "total": total, "papers": 0, "error": "No papers"}

    # Stage 2 – Rerank
    t0 = time.perf_counter()
    top = await rerank_papers(query, candidates, top_k=TOP_K)
    s2 = time.perf_counter() - t0
    stages["Semantic Rerank"] = s2
    print(f"    Stage 2 | Semantic Rerank      {s2:6.2f}s  →  top {len(top)} selected")

    # Stage 3 – PDF / Abstract
    t0 = time.perf_counter()
    texts = await get_paper_texts(top)
    s3 = time.perf_counter() - t0
    stages["PDF/Abstract Fetch"] = s3
    print(f"    Stage 3 | PDF/Abstract Fetch   {s3:6.2f}s  →  {len(texts)} texts retrieved")

    total = time.perf_counter() - wall
    print(f"  {SEP}")
    print(f"    TOTAL (Stages 1–3)             {total:6.2f}s")

    return {
        "query": query,
        "stages": stages,
        "total": total,
        "papers_found": len(candidates),
        "top_papers": len(top),
        "texts": len(texts),
        "error": None,
    }


# ─── master runner ────────────────────────────────────────────────────────────
async def main():
    hdr("RAGG AGENT — 5-Query Search Timing Benchmark")
    print(f"  Timestamp : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Queries   : {len(QUERIES)}")
    print(f"  Candidates: {ARXIV_CANDIDATES} per search  |  Top-K: {TOP_K}")
    print(f"  Stages    : arXiv Search → Semantic Rerank → PDF/Abstract Fetch")
    print(f"\n  Queries to benchmark:")
    for i, q in enumerate(QUERIES, 1):
        print(f"    {i}. {q}")

    # Pre-load reranker model so it doesn't skew timing
    print(f"\n  Pre-loading reranker model ...", end="", flush=True)
    _get_model()
    print(" done\n")

    results = []
    grand_start = time.perf_counter()

    hdr("Running Benchmarks")
    for idx, query in enumerate(QUERIES, 1):
        res = await benchmark_query(query, idx)
        results.append(res)

    grand_total = time.perf_counter() - grand_start

    # ─── Summary Table ─────────────────────────────────────────────────────────
    hdr("BENCHMARK RESULTS SUMMARY")

    # Header row
    print(f"  {'#':<3}  {'Query':<36}  {'arXiv':>7}  {'Rerank':>7}  {'PDF':>7}  {'TOTAL':>8}  {'Papers':>6}")
    print(f"  {SEP}")

    for i, r in enumerate(results, 1):
        s = r["stages"]
        s1 = s.get("arXiv Search",       0.0)
        s2 = s.get("Semantic Rerank",     0.0)
        s3 = s.get("PDF/Abstract Fetch",  0.0)
        tot = r["total"]
        q_short = r["query"][:34] + ".." if len(r["query"]) > 34 else r["query"]
        marker = "<< fastest" if r == min(results, key=lambda x: x["total"]) else \
                 "<< slowest" if r == max(results, key=lambda x: x["total"]) else ""
        print(f"  {i:<3}  {q_short:<36}  {s1:>6.2f}s  {s2:>6.2f}s  {s3:>6.2f}s  {tot:>7.2f}s  {r.get('papers_found',0):>6}  {marker}")

    print(f"  {SEP}")

    # Totals row
    avg = grand_total / len(results)
    print(f"  {'':3}  {'AVERAGE':36}  {'':>7}  {'':>7}  {'':>7}  {avg:>7.2f}s")
    print(f"  {'':3}  {'GRAND TOTAL (all 5 searches)':36}  {'':>7}  {'':>7}  {'':>7}  {grand_total:>7.2f}s")

    # ─── Visual Bar Chart ──────────────────────────────────────────────────────
    print(f"\n  Response Time Bar Chart  (each █ ≈ 0.3s)")
    print(f"  {SEP}")
    for r in results:
        q_label = r["query"][:25].ljust(26)
        bar, pct = progress_bar(r["total"], max(x["total"] for x in results), width=30)
        print(f"  {q_label}  {bar}  {r['total']:5.2f}s")

    # ─── Stage Distribution ────────────────────────────────────────────────────
    print(f"\n  Stage Contribution (averaged across 5 queries):")
    print(f"  {SEP}")
    stage_avgs = {
        "arXiv Search":       sum(r["stages"].get("arXiv Search",      0) for r in results) / len(results),
        "Semantic Rerank":    sum(r["stages"].get("Semantic Rerank",    0) for r in results) / len(results),
        "PDF/Abstract Fetch": sum(r["stages"].get("PDF/Abstract Fetch", 0) for r in results) / len(results),
    }
    avg_total = sum(stage_avgs.values())
    for stage, val in stage_avgs.items():
        bar, pct = progress_bar(val, avg_total, width=28)
        print(f"  {stage:<22}  {val:5.2f}s  {bar}  {pct:4.1f}%")

    # ─── Final Verdict ─────────────────────────────────────────────────────────
    fastest = min(results, key=lambda x: x["total"])
    slowest = max(results, key=lambda x: x["total"])

    print(f"\n  {'─'*50}")
    print(f"  Fastest : \"{fastest['query']}\"  →  {fastest['total']:.2f}s")
    print(f"  Slowest : \"{slowest['query']}\"  →  {slowest['total']:.2f}s")
    print(f"  Average : {avg:.2f}s per search")
    print(f"  Total   : {grand_total:.2f}s for all 5 searches")

    TARGET = 10.0
    passed = sum(1 for r in results if r["total"] <= TARGET)
    status = "PASS" if passed == len(results) else f"{passed}/{len(results)} under {TARGET}s"
    print(f"\n  Target ≤ {TARGET}s per search  →  {status}")
    print(f"\n  NOTE: Gemini Extraction (Stage 4) and Knowledge Graph (Stage 5)")
    print(f"        were skipped — your free-tier quota (20 req/day) is exhausted.")
    print(f"        Typical add-on: Stage 4 ~15–40s, Stage 5 ~3–8s.\n")

    hdr("Benchmark Complete")


if __name__ == "__main__":
    asyncio.run(main())

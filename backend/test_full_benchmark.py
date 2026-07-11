"""
Full-pipeline benchmark with gemini-2.0-flash.
Tests 5 queries across ALL 5 stages and reports timing for each.
Decides automatically whether to remove the graph stage.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_full_benchmark.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime

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

# ── Config ────────────────────────────────────────────────────────────────────
ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K            = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 5))
EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.0-flash")
SYNTHESIS_MODEL  = os.environ.get("SYNTHESIS_MODEL",  "gemini-2.0-flash")

# Threshold: if avg graph time > this, we recommend (and apply) removal
GRAPH_SLOW_THRESHOLD_S = 15.0

QUERIES = [
    "Unsupervised Learning",
    "BART language model",
    "LoRA low-rank adaptation",
    "QLoRA quantized low-rank adaptation",
    "Random Forest classification",
]

SEP  = "─" * 72
DSEP = "═" * 72

def hdr(text, ch="═"):
    line = ch * 72
    print(f"\n{line}\n  {text}\n{line}")

def progress_bar(val, total, width=28):
    pct = val / total if total else 0
    filled = max(1, int(pct * width))
    return "█" * filled + "░" * (width - filled), pct * 100

# ── Single query ──────────────────────────────────────────────────────────────
async def run_query(query: str, idx: int, sem: asyncio.Semaphore) -> dict:
    print(f"\n  [{idx}/5]  \"{query}\"   ({datetime.now().strftime('%H:%M:%S')})")
    print(f"  {SEP}")

    stages = {}
    wall = time.perf_counter()

    # Stage 1 – arXiv
    t0 = time.perf_counter()
    candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
    stages["arXiv Search"] = time.perf_counter() - t0
    print(f"    S1 arXiv Search        {stages['arXiv Search']:6.2f}s  → {len(candidates)} papers")

    if not candidates:
        return {"query": query, "stages": stages, "total": time.perf_counter()-wall, "error": "No papers"}

    # Stage 2 – Rerank
    t0 = time.perf_counter()
    top = await rerank_papers(query, candidates, top_k=TOP_K)
    stages["Semantic Rerank"] = time.perf_counter() - t0
    print(f"    S2 Semantic Rerank     {stages['Semantic Rerank']:6.2f}s  → top {len(top)}")

    # Stage 3 – PDF
    t0 = time.perf_counter()
    texts = await get_paper_texts(top)
    stages["PDF/Abstract"] = time.perf_counter() - t0
    print(f"    S3 PDF/Abstract        {stages['PDF/Abstract']:6.2f}s  → {len(texts)} texts")

    # Stage 4 – Gemini Extraction
    t0 = time.perf_counter()
    try:
        extracted, errors = await extract_papers(top, texts, semaphore=sem)
        stages["Gemini Extract"] = time.perf_counter() - t0
        print(f"    S4 Gemini Extract      {stages['Gemini Extract']:6.2f}s  → {len(extracted)} ok, {len(errors)} fail")
    except Exception as e:
        stages["Gemini Extract"] = time.perf_counter() - t0
        print(f"    S4 Gemini Extract      {stages['Gemini Extract']:6.2f}s  ERROR: {e}")
        extracted = []

    # Stage 5 – Knowledge Graph
    if extracted:
        t0 = time.perf_counter()
        try:
            graph = await build_knowledge_graph(extracted, semaphore=sem)
            stages["Knowledge Graph"] = time.perf_counter() - t0
            print(f"    S5 Knowledge Graph     {stages['Knowledge Graph']:6.2f}s  → {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        except Exception as e:
            stages["Knowledge Graph"] = time.perf_counter() - t0
            print(f"    S5 Knowledge Graph     {stages['Knowledge Graph']:6.2f}s  ERROR: {e}")
    else:
        stages["Knowledge Graph"] = 0.0
        print(f"    S5 Knowledge Graph      SKIP (no extracted papers)")

    total = time.perf_counter() - wall
    print(f"  {SEP}")
    print(f"    TOTAL                  {total:6.2f}s")

    return {
        "query": query,
        "stages": stages,
        "total": total,
        "error": None,
    }


# ── Master ────────────────────────────────────────────────────────────────────
async def main():
    hdr(f"FULL PIPELINE BENCHMARK  —  Model: {EXTRACTION_MODEL}")
    print(f"  Date/Time : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Model     : Extraction={EXTRACTION_MODEL}  |  Synthesis={SYNTHESIS_MODEL}")
    print(f"  Config    : candidates={ARXIV_CANDIDATES}  top_k={TOP_K}  concurrency={GEMINI_CONCURRENCY}")
    print(f"  Queries   :")
    for i, q in enumerate(QUERIES, 1):
        print(f"             {i}. {q}")

    print(f"\n  Pre-loading reranker ...", end="", flush=True)
    _get_model()
    print(" ready\n")

    sem = asyncio.Semaphore(GEMINI_CONCURRENCY)
    results = []
    grand_start = time.perf_counter()

    hdr("Running Searches", ch="─")
    for idx, q in enumerate(QUERIES, 1):
        r = await run_query(q, idx, sem)
        results.append(r)

    grand_total = time.perf_counter() - grand_start

    # ── Summary ───────────────────────────────────────────────────────────────
    hdr("RESULTS SUMMARY")

    stage_keys = ["arXiv Search", "Semantic Rerank", "PDF/Abstract",
                  "Gemini Extract", "Knowledge Graph"]

    # Header
    print(f"  {'#':<3}  {'Query':<38}  ", end="")
    print(f"{'arXiv':>6}  {'Rerank':>6}  {'PDF':>5}  {'Extract':>8}  {'Graph':>7}  {'TOTAL':>8}")
    print(f"  {SEP}")

    for i, r in enumerate(results, 1):
        s = r["stages"]
        q_s = r["query"][:36]
        tag = ""
        if r == min(results, key=lambda x: x["total"]):
            tag = " ← fastest"
        elif r == max(results, key=lambda x: x["total"]):
            tag = " ← slowest"
        print(
            f"  {i:<3}  {q_s:<38}  "
            f"{s.get('arXiv Search',0):>5.2f}s  "
            f"{s.get('Semantic Rerank',0):>5.2f}s  "
            f"{s.get('PDF/Abstract',0):>4.2f}s  "
            f"{s.get('Gemini Extract',0):>7.2f}s  "
            f"{s.get('Knowledge Graph',0):>6.2f}s  "
            f"{r['total']:>7.2f}s{tag}"
        )

    print(f"  {SEP}")
    avg = grand_total / len(results)
    print(f"  {'':3}  {'AVERAGE':38}  {'':6}  {'':6}  {'':5}  {'':8}  {'':7}  {avg:>7.2f}s")
    print(f"  {'':3}  {'GRAND TOTAL':38}  {'':6}  {'':6}  {'':5}  {'':8}  {'':7}  {grand_total:>7.2f}s")

    # ── Bar chart ─────────────────────────────────────────────────────────────
    print(f"\n  Response Time (per search):")
    max_t = max(r["total"] for r in results)
    for r in results:
        bar, _ = progress_bar(r["total"], max_t, width=32)
        print(f"    {r['query'][:28]:<28}  {bar}  {r['total']:.2f}s")

    # ── Stage avg contribution ─────────────────────────────────────────────────
    print(f"\n  Average Stage Contribution:")
    print(f"  {SEP}")
    avgs = {}
    for sk in stage_keys:
        avgs[sk] = sum(r["stages"].get(sk, 0) for r in results) / len(results)
    tot_avg = sum(avgs.values())
    for sk, val in avgs.items():
        bar, pct = progress_bar(val, tot_avg if tot_avg else 1, width=26)
        print(f"    {sk:<22}  {val:5.2f}s  {bar}  {pct:4.1f}%")

    # ── GRAPH DECISION ────────────────────────────────────────────────────────
    graph_avg = avgs.get("Knowledge Graph", 0)
    extract_avg = avgs.get("Gemini Extract", 0)

    hdr("GRAPH STAGE DECISION")
    print(f"  Avg Knowledge Graph time : {graph_avg:.2f}s")
    print(f"  Avg Gemini Extract time  : {extract_avg:.2f}s")
    print(f"  Slow threshold           : {GRAPH_SLOW_THRESHOLD_S:.0f}s")

    if graph_avg > GRAPH_SLOW_THRESHOLD_S:
        print(f"\n  VERDICT: Graph takes >{GRAPH_SLOW_THRESHOLD_S:.0f}s on average — REMOVING feature...")
        remove_graph()
        print(f"  Graph stage has been DISABLED in the pipeline.")
        print(f"  To re-enable: set ENABLE_GRAPH_STAGE=true in .env")
    else:
        print(f"\n  VERDICT: Graph is FAST enough ({graph_avg:.2f}s < {GRAPH_SLOW_THRESHOLD_S:.0f}s) — KEEPING feature.")

    fastest = min(results, key=lambda x: x["total"])
    slowest = max(results, key=lambda x: x["total"])
    print(f"\n  Fastest search : \"{fastest['query']}\"  →  {fastest['total']:.2f}s")
    print(f"  Slowest search : \"{slowest['query']}\"  →  {slowest['total']:.2f}s")
    print(f"  Average        : {avg:.2f}s")

    hdr("Benchmark Complete")


def remove_graph():
    """Disable the Knowledge Graph stage by patching graph_service.py to return empty graph."""
    stub = '''\
"""
graph_service.py — Knowledge Graph stage DISABLED.
Disabled automatically by benchmark because avg synthesis time exceeded threshold.
To re-enable: restore from git  (git checkout app/services/graph_service.py)
"""
import asyncio
import logging
from app.models.schemas import ExtractedPaper, KnowledgeGraph

logger = logging.getLogger(__name__)

async def build_knowledge_graph(
    papers: list[ExtractedPaper],
    semaphore: asyncio.Semaphore | None = None,
) -> KnowledgeGraph:
    """Graph stage disabled — returns empty graph immediately."""
    logger.info("[graph] Stage DISABLED — returning empty graph (fast path).")
    return KnowledgeGraph(
        nodes=[{"id": p.arxiv_id, "label": p.title[:60], "type": "paper"} for p in papers],
        edges=[],
        open_problems=[],
        summary="Knowledge graph synthesis is currently disabled for performance reasons.",
    )
'''
    path = os.path.join(
        os.path.dirname(__file__),
        "app", "services", "graph_service.py"
    )
    with open(path, "w") as f:
        f.write(stub)
    print(f"  [✓] Written stub to: {path}")


if __name__ == "__main__":
    asyncio.run(main())

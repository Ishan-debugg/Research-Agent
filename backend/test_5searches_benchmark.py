"""
Benchmark: Test 5 different searches through the full RAGG pipeline
and measure time taken for each search to respond.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_5searches_benchmark.py
"""

import asyncio
import os
import sys
import time
from datetime import datetime

# --- load .env so GEMINI_API_KEY is available ---
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
_key = os.environ.get("GEMINI_API_KEY")
if not _key:
    sys.exit("ERROR: GEMINI_API_KEY not set. Create backend/.env with your key.")
genai.configure(api_key=_key)

from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers, _get_model
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service import build_knowledge_graph

# ── Configuration ─────────────────────────────────────────────────────────────
ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 5))

QUERIES = [
    "Unsupervised Learning",
    "BART language model",
    "LoRA low-rank adaptation",
    "QLoRA quantized low-rank adaptation",
    "Random Forest classification",
]

# ── Helpers ───────────────────────────────────────────────────────────────────
COLORS = {
    "RESET":  "\033[0m",
    "BOLD":   "\033[1m",
    "CYAN":   "\033[96m",
    "GREEN":  "\033[92m",
    "YELLOW": "\033[93m",
    "RED":    "\033[91m",
    "MAGENTA":"\033[95m",
    "WHITE":  "\033[97m",
    "BLUE":   "\033[94m",
}
C = COLORS

def banner(text, color="CYAN"):
    line = "═" * 70
    print(f"\n{C[color]}{C['BOLD']}{line}")
    print(f"  {text}")
    print(f"{line}{C['RESET']}")

def section(label, value, color="WHITE"):
    print(f"  {C[color]}{label:<35}{C['RESET']} {value}")

def bar_chart(stages, total):
    print(f"\n  {C['BOLD']}Stage Breakdown:{C['RESET']}")
    for name, t in stages:
        pct = (t / total * 100) if total > 0 else 0
        filled = max(1, int(pct / 3))
        bar = "█" * filled + "░" * (33 - filled)
        color = "GREEN" if pct < 20 else "YELLOW" if pct < 40 else "RED"
        print(f"    {name:<12} {t:5.2f}s  {C[color]}{bar}{C['RESET']}  {pct:4.1f}%")

# ── Per-query pipeline ────────────────────────────────────────────────────────
async def run_single_query(query: str, sem: asyncio.Semaphore, idx: int) -> dict:
    banner(f"[{idx}/5] Query: \"{query}\"", color="MAGENTA")
    print(f"  {C['BLUE']}Started at: {datetime.now().strftime('%H:%M:%S')}{C['RESET']}\n")

    result = {
        "query": query,
        "stages": {},
        "papers_found": 0,
        "top_papers": 0,
        "nodes": 0,
        "edges": 0,
        "total": 0.0,
        "error": None,
    }

    wall_start = time.perf_counter()

    try:
        # ── Stage 1: arXiv Search ─────────────────────────────────────────────
        t0 = time.perf_counter()
        candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
        s1 = time.perf_counter() - t0
        result["stages"]["arXiv Search"] = s1
        result["papers_found"] = len(candidates)
        section(f"[Stage 1] arXiv Search", f"{s1:.2f}s  →  {len(candidates)} papers", "CYAN")

        if not candidates:
            result["error"] = "No papers found on arXiv"
            result["total"] = time.perf_counter() - wall_start
            return result

        # ── Stage 2: Semantic Rerank ──────────────────────────────────────────
        t0 = time.perf_counter()
        top = await rerank_papers(query, candidates, top_k=TOP_K)
        s2 = time.perf_counter() - t0
        result["stages"]["Semantic Rerank"] = s2
        result["top_papers"] = len(top)
        section(f"[Stage 2] Semantic Rerank", f"{s2:.2f}s  →  top {len(top)} papers", "CYAN")

        # ── Stage 3: PDF / Abstract Fetch ─────────────────────────────────────
        t0 = time.perf_counter()
        texts = await get_paper_texts(top)
        s3 = time.perf_counter() - t0
        result["stages"]["PDF/Abstract Fetch"] = s3
        section(f"[Stage 3] PDF/Abstract Fetch", f"{s3:.2f}s  →  {len(texts)} texts", "CYAN")

        # ── Stage 4: Gemini Extraction ────────────────────────────────────────
        t0 = time.perf_counter()
        extracted, errors = await extract_papers(top, texts, semaphore=sem)
        s4 = time.perf_counter() - t0
        result["stages"]["Gemini Extraction"] = s4
        section(f"[Stage 4] Gemini Extraction", f"{s4:.2f}s  →  {len(extracted)} ok, {len(errors)} errors", "CYAN")

        # ── Stage 5: Knowledge Graph ──────────────────────────────────────────
        t0 = time.perf_counter()
        graph = await build_knowledge_graph(extracted, semaphore=sem)
        s5 = time.perf_counter() - t0
        result["stages"]["Knowledge Graph"] = s5
        result["nodes"] = len(graph.nodes)
        result["edges"] = len(graph.edges)
        section(f"[Stage 5] Knowledge Graph", f"{s5:.2f}s  →  {len(graph.nodes)} nodes, {len(graph.edges)} edges", "CYAN")

    except Exception as e:
        result["error"] = str(e)
        print(f"\n  {C['RED']}ERROR: {e}{C['RESET']}")

    result["total"] = time.perf_counter() - wall_start

    # Stage bar chart
    if result["stages"]:
        bar_chart(list(result["stages"].items()), result["total"])

    print(f"\n  {C['GREEN']}{C['BOLD']}Total Response Time: {result['total']:.2f}s{C['RESET']}")

    return result


# ── Master runner ─────────────────────────────────────────────────────────────
async def run_all():
    banner("RAGG AGENT — 5-Query Search Benchmark", color="CYAN")
    print(f"  {C['WHITE']}Queries to test:{C['RESET']}")
    for i, q in enumerate(QUERIES, 1):
        print(f"    {i}. {q}")
    print(f"\n  {C['WHITE']}Config: candidates={ARXIV_CANDIDATES}  top_k={TOP_K}  concurrency={GEMINI_CONCURRENCY}{C['RESET']}")

    # Preload the reranker model once
    print(f"\n  {C['YELLOW']}Pre-loading reranker model...{C['RESET']}", end="", flush=True)
    _get_model()
    print(f" {C['GREEN']}done{C['RESET']}")

    sem = asyncio.Semaphore(GEMINI_CONCURRENCY)
    all_results = []
    grand_start = time.perf_counter()

    for idx, query in enumerate(QUERIES, 1):
        res = await run_single_query(query, sem, idx)
        all_results.append(res)

    grand_total = time.perf_counter() - grand_start

    # ── Summary Table ──────────────────────────────────────────────────────────
    banner("BENCHMARK SUMMARY — All 5 Searches", color="YELLOW")

    col_w = [30, 10, 10, 10, 10, 10, 12]
    headers = ["Query", "arXiv", "Rerank", "PDF", "Extract", "Graph", "TOTAL"]
    sep = "─" * (sum(col_w) + len(col_w) * 3 + 1)

    print(f"  {C['BOLD']}", end="")
    for h, w in zip(headers, col_w):
        print(f"{h:<{w}}", end="  ")
    print(C["RESET"])
    print(f"  {sep}")

    TARGET = 30.0
    fastest = None
    slowest = None

    for r in all_results:
        total = r["total"]
        stages = r["stages"]
        color = "GREEN" if total <= TARGET else "RED"

        short_query = r["query"][:28] + ".." if len(r["query"]) > 28 else r["query"]
        row = [
            short_query,
            f"{stages.get('arXiv Search', 0):.2f}s",
            f"{stages.get('Semantic Rerank', 0):.2f}s",
            f"{stages.get('PDF/Abstract Fetch', 0):.2f}s",
            f"{stages.get('Gemini Extraction', 0):.2f}s",
            f"{stages.get('Knowledge Graph', 0):.2f}s",
            f"{total:.2f}s",
        ]
        print(f"  {C[color]}", end="")
        for val, w in zip(row, col_w):
            print(f"{val:<{w}}", end="  ")
        print(C["RESET"])

        if fastest is None or total < fastest["total"]:
            fastest = r
        if slowest is None or total > slowest["total"]:
            slowest = r

    print(f"  {sep}")
    print(f"\n  {C['BOLD']}Grand Total (all 5 searches): {grand_total:.2f}s{C['RESET']}")
    print(f"  {C['BOLD']}Average per search:           {grand_total/len(all_results):.2f}s{C['RESET']}")

    if fastest:
        print(f"\n  {C['GREEN']}🚀 Fastest: \"{fastest['query']}\" — {fastest['total']:.2f}s{C['RESET']}")
    if slowest:
        print(f"  {C['RED']}🐢 Slowest: \"{slowest['query']}\" — {slowest['total']:.2f}s{C['RESET']}")

    # Target check
    passed = sum(1 for r in all_results if r["total"] <= TARGET)
    print(f"\n  {C['CYAN']}Target ≤ {TARGET}s: {passed}/{len(all_results)} searches passed{C['RESET']}")

    # Errors
    errors = [r for r in all_results if r.get("error")]
    if errors:
        print(f"\n  {C['RED']}Errors encountered:{C['RESET']}")
        for r in errors:
            print(f"    • {r['query']}: {r['error']}")

    banner("Benchmark Complete", color="GREEN")


if __name__ == "__main__":
    asyncio.run(run_all())

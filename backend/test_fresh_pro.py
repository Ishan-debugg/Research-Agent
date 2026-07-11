"""
Fresh benchmark with gemini-2.5-pro on 5 NEW queries never searched before.
Clears cache for these queries before running so results are cold-path / real.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_fresh_pro.py
"""

import asyncio
import os
import sys
import time
import sqlite3
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
_key = os.environ.get("GEMINI_API_KEY")
if not _key:
    sys.exit("ERROR: GEMINI_API_KEY not set.")
genai.configure(api_key=_key)

EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.5-pro")
SYNTHESIS_MODEL  = os.environ.get("SYNTHESIS_MODEL",  "gemini-2.5-pro")

from app.services.arxiv_service   import search_arxiv
from app.services.rerank_service  import rerank_papers, _get_model
from app.services.pdf_service     import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service   import build_knowledge_graph
from app.services                 import cache_service

# ── 5 FRESH queries — never searched in previous tests ────────────────────────
QUERIES = [
    "Diffusion Transformer image generation",
    "Mixture of Experts sparse language model",
    "Vision Language Model multimodal reasoning",
    "Retrieval Augmented Generation RAG pipeline",
    "Graph Neural Network molecular property prediction",
]

ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K            = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 3))  # lower for Pro
GRAPH_SLOW_S     = 15.0   # threshold to flag graph as slow

SEP  = "─" * 74
DSEP = "═" * 74

# ── Helpers ───────────────────────────────────────────────────────────────────
def hdr(text):
    print(f"\n{DSEP}\n  {text}\n{DSEP}")

def bar(val, mx, width=30):
    pct = val / mx if mx else 0
    filled = max(1, int(pct * width))
    return "█" * filled + "░" * (width - filled), pct * 100

def clear_cache_for_papers(paper_ids: list):
    """Remove cached extractions for specific arxiv IDs so we force fresh Gemini calls."""
    try:
        from app.services.cache_service import _get_conn
        conn = _get_conn()
        for pid in paper_ids:
            conn.execute("DELETE FROM paper_texts   WHERE arxiv_id=?", (pid,))
            conn.execute("DELETE FROM extractions   WHERE arxiv_id=?", (pid,))
        conn.commit()
    except Exception as e:
        print(f"  [cache clear] {e}")

# ── Single query run ──────────────────────────────────────────────────────────
async def run_query(query: str, idx: int, sem: asyncio.Semaphore) -> dict:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{idx}/5]  \"{query}\"")
    print(f"           Started: {ts}")
    print(f"  {SEP}")

    stages = {}
    wall   = time.perf_counter()

    # S1 – arXiv
    t0 = time.perf_counter()
    candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
    stages["arXiv Search"]  = time.perf_counter() - t0
    print(f"    Stage 1 | arXiv Search          {stages['arXiv Search']:6.2f}s  →  {len(candidates)} papers")

    if not candidates:
        return {"query": query, "stages": stages, "total": time.perf_counter()-wall, "error": "No papers"}

    # Clear cache so Gemini is actually called (cold path)
    clear_cache_for_papers([p.arxiv_id for p in candidates])

    # S2 – Rerank
    t0 = time.perf_counter()
    top = await rerank_papers(query, candidates, top_k=TOP_K)
    stages["Semantic Rerank"] = time.perf_counter() - t0
    print(f"    Stage 2 | Semantic Rerank        {stages['Semantic Rerank']:6.2f}s  →  top {len(top)} selected")

    # S3 – PDF
    t0 = time.perf_counter()
    texts = await get_paper_texts(top)
    stages["PDF/Abstract"]  = time.perf_counter() - t0
    print(f"    Stage 3 | PDF/Abstract Fetch     {stages['PDF/Abstract']:6.2f}s  →  {len(texts)} texts")

    # S4 – Gemini Extraction
    t0 = time.perf_counter()
    try:
        extracted, errors = await extract_papers(top, texts, semaphore=sem)
        stages["Gemini Extract"] = time.perf_counter() - t0
        print(f"    Stage 4 | Gemini Extraction     {stages['Gemini Extract']:6.2f}s  →  {len(extracted)} ok / {len(errors)} fail")
    except Exception as e:
        stages["Gemini Extract"] = time.perf_counter() - t0
        print(f"    Stage 4 | Gemini Extraction     {stages['Gemini Extract']:6.2f}s  ERROR: {e}")
        extracted = []

    # S5 – Knowledge Graph
    if extracted:
        t0 = time.perf_counter()
        try:
            graph = await build_knowledge_graph(extracted, semaphore=sem)
            stages["Knowledge Graph"] = time.perf_counter() - t0
            print(f"    Stage 5 | Knowledge Graph       {stages['Knowledge Graph']:6.2f}s  →  {len(graph.nodes)} nodes / {len(graph.edges)} edges")
        except Exception as e:
            stages["Knowledge Graph"] = time.perf_counter() - t0
            print(f"    Stage 5 | Knowledge Graph       {stages['Knowledge Graph']:6.2f}s  ERROR: {e}")
    else:
        stages["Knowledge Graph"] = 0.0
        print(f"    Stage 5 | Knowledge Graph        SKIPPED (extraction failed)")

    total = time.perf_counter() - wall
    print(f"  {SEP}")
    print(f"    ⏱  TOTAL                          {total:6.2f}s")

    return {"query": query, "stages": stages, "total": total, "error": None}


# ── Master ────────────────────────────────────────────────────────────────────
async def main():
    hdr(f"RAGG — FRESH 5-QUERY BENCHMARK  |  Model: {EXTRACTION_MODEL}")
    print(f"  Timestamp  : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Model      : {EXTRACTION_MODEL}  (latest Gemini Pro)")
    print(f"  Candidates : {ARXIV_CANDIDATES}  |  Top-K: {TOP_K}  |  Concurrency: {GEMINI_CONCURRENCY}")
    print(f"  Cache      : CLEARED for these queries (true cold-path test)")
    print(f"\n  New queries (not previously searched):")
    for i, q in enumerate(QUERIES, 1):
        print(f"    {i}. {q}")

    print(f"\n  Loading reranker ...", end="", flush=True)
    _get_model()
    print(" ready")

    sem     = asyncio.Semaphore(GEMINI_CONCURRENCY)
    results = []
    g_start = time.perf_counter()

    hdr("Running Searches")
    for idx, q in enumerate(QUERIES, 1):
        r = await run_query(q, idx, sem)
        results.append(r)

    grand_total = time.perf_counter() - g_start

    # ── Summary table ─────────────────────────────────────────────────────────
    hdr("BENCHMARK RESULTS  —  gemini-2.5-pro")

    print(f"  {'#':<3}  {'Query':<42}  {'arXiv':>6}  {'Rerank':>6}  {'PDF':>5}  {'Extract':>8}  {'Graph':>7}  {'TOTAL':>8}")
    print(f"  {SEP}")

    for i, r in enumerate(results, 1):
        s   = r["stages"]
        q_s = r["query"][:40]
        tag = " ← fastest" if r["total"] == min(x["total"] for x in results) else \
              " ← slowest" if r["total"] == max(x["total"] for x in results) else ""
        print(
            f"  {i:<3}  {q_s:<42}  "
            f"{s.get('arXiv Search',0):>5.2f}s  "
            f"{s.get('Semantic Rerank',0):>5.2f}s  "
            f"{s.get('PDF/Abstract',0):>4.2f}s  "
            f"{s.get('Gemini Extract',0):>7.2f}s  "
            f"{s.get('Knowledge Graph',0):>6.2f}s  "
            f"{r['total']:>7.2f}s{tag}"
        )

    print(f"  {SEP}")
    avg = grand_total / len(results)
    print(f"  {'':3}  {'AVERAGE':42}  {'':>6}  {'':>6}  {'':>5}  {'':>8}  {'':>7}  {avg:>7.2f}s")
    print(f"  {'':3}  {'GRAND TOTAL (all 5 searches)':42}  {'':>6}  {'':>6}  {'':>5}  {'':>8}  {'':>7}  {grand_total:>7.2f}s")

    # ── Bar chart ─────────────────────────────────────────────────────────────
    print(f"\n  Response-Time Bar Chart:")
    mx = max(r["total"] for r in results)
    for r in results:
        b, _ = bar(r["total"], mx, width=32)
        tag = "✅" if r["total"] <= 30 else "⚠️ "
        print(f"  {tag} {r['query'][:30]:<30}  {b}  {r['total']:5.2f}s")

    # ── Stage averages ────────────────────────────────────────────────────────
    stage_keys = ["arXiv Search","Semantic Rerank","PDF/Abstract","Gemini Extract","Knowledge Graph"]
    avgs = {k: sum(r["stages"].get(k,0) for r in results)/len(results) for k in stage_keys}
    tot_avg = sum(avgs.values()) or 1

    print(f"\n  Average Stage Time & Share:")
    print(f"  {SEP}")
    for k, v in avgs.items():
        b, pct = bar(v, tot_avg, width=26)
        print(f"    {k:<22}  {v:5.2f}s  {b}  {pct:4.1f}%")

    # ── Graph decision ────────────────────────────────────────────────────────
    graph_avg   = avgs["Knowledge Graph"]
    extract_avg = avgs["Gemini Extract"]

    hdr("GRAPH STAGE VERDICT")
    print(f"  Model used         : {EXTRACTION_MODEL}")
    print(f"  Avg Extract time   : {extract_avg:.2f}s")
    print(f"  Avg Graph time     : {graph_avg:.2f}s")
    print(f"  Slow threshold     : {GRAPH_SLOW_S:.0f}s")

    if graph_avg > GRAPH_SLOW_S:
        print(f"\n  ❌  Graph avg ({graph_avg:.2f}s) > {GRAPH_SLOW_S:.0f}s  →  REMOVING graph stage from pipeline")
        _disable_graph()
    else:
        print(f"\n  ✅  Graph avg ({graph_avg:.2f}s) ≤ {GRAPH_SLOW_S:.0f}s  →  KEEPING graph stage")

    fastest = min(results, key=lambda x: x["total"])
    slowest = max(results, key=lambda x: x["total"])
    print(f"\n  🚀 Fastest : \"{fastest['query']}\"  →  {fastest['total']:.2f}s")
    print(f"  🐢 Slowest : \"{slowest['query']}\"  →  {slowest['total']:.2f}s")
    print(f"  📊 Average : {avg:.2f}s per search")

    hdr("Benchmark Complete")


def _disable_graph():
    stub = '''\
"""
graph_service.py — DISABLED by benchmark (avg time exceeded threshold).
To restore: git checkout app/services/graph_service.py
"""
import asyncio, logging
from app.models.schemas import ExtractedPaper, KnowledgeGraph
logger = logging.getLogger(__name__)

async def build_knowledge_graph(
    papers: list[ExtractedPaper],
    semaphore: asyncio.Semaphore | None = None,
) -> KnowledgeGraph:
    logger.info("[graph] DISABLED — returning empty graph instantly.")
    return KnowledgeGraph(
        nodes=[{"id": p.arxiv_id, "label": p.title[:60], "type": "paper"} for p in papers],
        edges=[], open_problems=[],
        summary="Knowledge graph disabled for performance.",
    )
'''
    path = os.path.join(os.path.dirname(__file__), "app", "services", "graph_service.py")
    with open(path, "w") as f:
        f.write(stub)
    print(f"  [✓] Graph stub written → {path}")


if __name__ == "__main__":
    asyncio.run(main())

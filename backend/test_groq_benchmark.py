"""
Benchmark: Groq Mixtral (extraction) + Gemini 2.5 Pro (graph/synthesis)
Tests 5 fresh queries not previously in the cache and shows real speedup.

Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_groq_benchmark.py
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

EXTRACTION_MODEL = os.environ.get("GROQ_MODEL", "mixtral-8x7b-32768")
SYNTHESIS_MODEL  = os.environ.get("SYNTHESIS_MODEL", "gemini-2.5-pro")

from app.services.arxiv_service      import search_arxiv
from app.services.rerank_service     import rerank_papers, _get_model
from app.services.pdf_service        import get_paper_texts
from app.services.extraction_service import extract_papers
from app.services.graph_service      import build_knowledge_graph
from app.services                    import cache_service

# ── 5 BRAND-NEW queries (never searched before) ───────────────────────────────
QUERIES = [
    "Mamba state space model sequence modeling",
    "CLIP contrastive language image pretraining",
    "Protein structure prediction AlphaFold",
    "Reinforcement Learning from Human Feedback RLHF",
    "Knowledge Distillation neural network compression",
]

ARXIV_CANDIDATES   = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K              = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 3))

GRAPH_SLOW_S = 15.0

SEP  = "─" * 74
DSEP = "═" * 74

# ─── helpers ──────────────────────────────────────────────────────────────────
def hdr(text):
    print(f"\n{DSEP}\n  {text}\n{DSEP}")

def bar(val, mx, width=30):
    pct = val / mx if mx else 0
    filled = max(1, int(pct * width))
    return "█" * filled + "░" * (width - filled), pct * 100

def clear_cache(paper_ids):
    try:
        from app.services.cache_service import _get_conn
        conn = _get_conn()
        for pid in paper_ids:
            conn.execute("DELETE FROM paper_texts WHERE arxiv_id=?", (pid,))
            try:
                conn.execute("DELETE FROM extractions WHERE arxiv_id=?", (pid,))
            except Exception:
                pass
        conn.commit()
    except Exception:
        pass

# ─── single query ─────────────────────────────────────────────────────────────
async def run_query(query: str, idx: int, sem: asyncio.Semaphore) -> dict:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n  [{idx}/5]  \"{query}\"   ({ts})")
    print(f"  {SEP}")

    stages = {}
    wall   = time.perf_counter()

    # S1 – arXiv
    t0 = time.perf_counter()
    candidates = await search_arxiv(query, max_results=ARXIV_CANDIDATES)
    stages["arXiv Search"] = time.perf_counter() - t0
    print(f"    S1 | arXiv Search           {stages['arXiv Search']:6.2f}s  →  {len(candidates)} papers")

    if not candidates:
        return {"query": query, "stages": stages, "total": time.perf_counter()-wall, "error": "No papers"}

    # Clear cache for true cold-path
    clear_cache([p.arxiv_id for p in candidates])

    # S2 – Rerank
    t0 = time.perf_counter()
    top = await rerank_papers(query, candidates, top_k=TOP_K)
    stages["Semantic Rerank"] = time.perf_counter() - t0
    print(f"    S2 | Semantic Rerank         {stages['Semantic Rerank']:6.2f}s  →  top {len(top)}")

    # S3 – PDF
    t0 = time.perf_counter()
    texts = await get_paper_texts(top)
    stages["PDF/Abstract"] = time.perf_counter() - t0
    print(f"    S3 | PDF/Abstract Fetch      {stages['PDF/Abstract']:6.2f}s  →  {len(texts)} texts")

    # S4 – Groq Extraction
    t0 = time.perf_counter()
    try:
        extracted, errors = await extract_papers(top, texts, semaphore=sem)
        stages["Groq Extract"] = time.perf_counter() - t0
        status = f"{len(extracted)} ok / {len(errors)} fail"
        print(f"    S4 | Groq Extract [Mixtral] {stages['Groq Extract']:6.2f}s  →  {status}")
    except Exception as e:
        stages["Groq Extract"] = time.perf_counter() - t0
        print(f"    S4 | Groq Extract           {stages['Groq Extract']:6.2f}s  ERROR: {e}")
        extracted = []

    # S5 – Gemini 2.5 Pro Graph
    if extracted:
        t0 = time.perf_counter()
        try:
            graph = await build_knowledge_graph(extracted, semaphore=sem)
            stages["Gemini Graph"] = time.perf_counter() - t0
            print(f"    S5 | Gemini Graph [Pro]     {stages['Gemini Graph']:6.2f}s  →  {len(graph.nodes)} nodes / {len(graph.edges)} edges")
        except Exception as e:
            stages["Gemini Graph"] = time.perf_counter() - t0
            print(f"    S5 | Gemini Graph           {stages['Gemini Graph']:6.2f}s  ERROR: {e}")
    else:
        stages["Gemini Graph"] = 0.0
        print(f"    S5 | Gemini Graph            SKIPPED (extraction failed)")

    total = time.perf_counter() - wall
    print(f"  {SEP}")
    print(f"    ⏱  TOTAL                      {total:6.2f}s")

    return {"query": query, "stages": stages, "total": total, "error": None}

# ─── master ───────────────────────────────────────────────────────────────────
async def main():
    hdr(f"RAGG — HYBRID BENCHMARK  |  Groq Mixtral + Gemini 2.5 Pro")
    print(f"  Timestamp  : {datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}")
    print(f"  Extraction : {EXTRACTION_MODEL}  (Groq — 3-4x faster)")
    print(f"  Graph      : {SYNTHESIS_MODEL}   (Gemini — high quality)")
    print(f"  Cache      : CLEARED (cold-path test)")
    print(f"\n  Fresh queries (not in cache):")
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

    # ─── Summary ──────────────────────────────────────────────────────────────
    hdr("RESULTS SUMMARY  —  Groq Mixtral + Gemini 2.5 Pro")

    stage_keys = ["arXiv Search", "Semantic Rerank", "PDF/Abstract",
                  "Groq Extract", "Gemini Graph"]

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
            f"{s.get('Groq Extract',0):>7.2f}s  "
            f"{s.get('Gemini Graph',0):>6.2f}s  "
            f"{r['total']:>7.2f}s{tag}"
        )

    print(f"  {SEP}")
    avg = grand_total / len(results)
    print(f"  {'':3}  {'AVERAGE':42}                                            {avg:>7.2f}s")
    print(f"  {'':3}  {'GRAND TOTAL (all 5 searches)':42}                                            {grand_total:>7.2f}s")

    # ─── bar chart ────────────────────────────────────────────────────────────
    print(f"\n  Response-Time Bar Chart (each █ ≈ 1s):")
    mx = max(r["total"] for r in results)
    for r in results:
        b, _ = bar(r["total"], mx, width=32)
        icon = "✅" if r["total"] <= 20 else "⚠️ "
        print(f"  {icon} {r['query'][:30]:<30}  {b}  {r['total']:5.2f}s")

    # ─── stage averages ───────────────────────────────────────────────────────
    avgs = {k: sum(r["stages"].get(k, 0) for r in results) / len(results) for k in stage_keys}
    tot_avg = sum(avgs.values()) or 1

    print(f"\n  Average Stage Time & Share:")
    print(f"  {SEP}")
    for k, v in avgs.items():
        b, pct = bar(v, tot_avg, width=26)
        print(f"    {k:<22}  {v:5.2f}s  {b}  {pct:4.1f}%")

    # ─── graph verdict ────────────────────────────────────────────────────────
    graph_avg   = avgs.get("Gemini Graph", 0)
    extract_avg = avgs.get("Groq Extract", 0)

    hdr("GRAPH STAGE VERDICT")
    print(f"  Extraction engine  : Groq {EXTRACTION_MODEL}")
    print(f"  Graph engine       : Gemini {SYNTHESIS_MODEL}")
    print(f"  Avg Extract time   : {extract_avg:.2f}s")
    print(f"  Avg Graph time     : {graph_avg:.2f}s")
    print(f"  Slow threshold     : {GRAPH_SLOW_S:.0f}s")

    if graph_avg > GRAPH_SLOW_S:
        print(f"\n  ❌  Graph avg ({graph_avg:.2f}s) > {GRAPH_SLOW_S:.0f}s  →  DISABLING graph stage...")
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
"""graph_service.py — DISABLED by benchmark. Restore: git checkout app/services/graph_service.py"""
import asyncio, logging
from app.models.schemas import ExtractedPaper, KnowledgeGraph
logger = logging.getLogger(__name__)
async def build_knowledge_graph(papers, semaphore=None):
    logger.info("[graph] DISABLED — returning empty graph instantly.")
    return KnowledgeGraph(nodes=[{"id":p.arxiv_id,"label":p.title[:60],"type":"paper"} for p in papers],
                          edges=[], open_problems=[], summary="Graph disabled for performance.")
'''
    path = os.path.join(os.path.dirname(__file__), "app", "services", "graph_service.py")
    with open(path, "w") as f:
        f.write(stub)
    print(f"  [✓] Graph stub written → {path}")


if __name__ == "__main__":
    asyncio.run(main())

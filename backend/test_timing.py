"""
Timing benchmark for the full 5-stage pipeline.
Run from the backend directory:
    .\\venv\\Scripts\\python.exe test_timing.py
"""
import asyncio
import os
import sys
import time

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
from app.services import cache_service

QUERY = "transformer attention mechanism for image classification"
ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K = int(os.environ.get("TOP_K_PAPERS", 5))
GEMINI_CONCURRENCY = int(os.environ.get("GEMINI_CONCURRENCY", 5))

def hdr(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)

async def run():
    sem = asyncio.Semaphore(GEMINI_CONCURRENCY)

    # Preload reranker (same as startup does)
    _get_model()

    hdr(f"Pipeline timing  —  query: '{QUERY}'")
    print(f"  candidates={ARXIV_CANDIDATES}  top_k={TOP_K}  concurrency={GEMINI_CONCURRENCY}")
    print(f"  ENRICH_WITH_PDF={os.environ.get('ENRICH_WITH_PDF','false')}\n")

    wall = time.perf_counter()

    # ── Stage 1: arXiv ────────────────────────────────────────────────────────
    t0 = time.perf_counter()
    candidates = await search_arxiv(QUERY, max_results=ARXIV_CANDIDATES)
    s1 = time.perf_counter() - t0
    print(f"  [Stage 1] arXiv retrieve        {s1:6.2f}s  →  {len(candidates)} papers")
    if not candidates:
        print("  No papers found — aborting.")
        return

    # ── Stage 2: Rerank ───────────────────────────────────────────────────────
    t0 = time.perf_counter()
    top = await rerank_papers(QUERY, candidates, top_k=TOP_K)
    s2 = time.perf_counter() - t0
    print(f"  [Stage 2] Semantic rerank       {s2:6.2f}s  →  top {len(top)} papers")

    # Clear per-paper text cache so we benchmark the real cold path
    print("  (clearing paper text cache for cold-path test...)")
    for p in top:
        try:
            import sqlite3
            from app.services.cache_service import _get_conn
            conn = _get_conn()
            conn.execute("DELETE FROM paper_texts WHERE arxiv_id=?", (p.arxiv_id,))
            conn.commit()
        except Exception:
            pass

    # ── Stage 3: PDF / abstract ───────────────────────────────────────────────
    t0 = time.perf_counter()
    texts = await get_paper_texts(top)
    s3 = time.perf_counter() - t0
    print(f"  [Stage 3] PDF/abstract fetch    {s3:6.2f}s  →  {len(texts)} texts")

    # ── Stage 4: Gemini extraction ────────────────────────────────────────────
    t0 = time.perf_counter()
    extracted, errors = await extract_papers(top, texts, semaphore=sem)
    s4 = time.perf_counter() - t0
    print(f"  [Stage 4] Gemini extraction     {s4:6.2f}s  →  {len(extracted)} ok, {len(errors)} errors")

    # ── Stage 5: Knowledge graph synthesis ───────────────────────────────────
    t0 = time.perf_counter()
    graph = await build_knowledge_graph(extracted, semaphore=sem)
    s5 = time.perf_counter() - t0
    print(f"  [Stage 5] Graph synthesis       {s5:6.2f}s  →  {len(graph.nodes)} nodes, {len(graph.edges)} edges")

    total = time.perf_counter() - wall
    print(f"\n  {'─'*50}")
    print(f"  TOTAL                           {total:6.2f}s")

    target = 30.0
    icon = "✅" if total <= target else "⚠️ "
    print(f"  {icon}  Target ≤ {target}s  →  {'PASS' if total <= target else 'NEEDS WORK'}")

    # Per-stage breakdown
    stages = [
        ("arXiv",     s1),
        ("Rerank",    s2),
        ("PDFs",      s3),
        ("Extract",   s4),
        ("Graph",     s5),
    ]
    print(f"\n  Breakdown (% of total):")
    for name, t in stages:
        bar_len = max(1, int(t / total * 30))
        bar = "█" * bar_len
        pct = t / total * 100
        print(f"    {name:<10} {t:5.2f}s  {pct:4.0f}%  {bar}")

if __name__ == "__main__":
    asyncio.run(run())

"""
Test extraction on the exact query that was failing.
Run from backend dir:  .\\venv\\Scripts\\python.exe test_extraction_fix.py
"""
import asyncio, os, sys
from dotenv import load_dotenv
load_dotenv()

import google.generativeai as genai
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

from app.services.arxiv_service import search_arxiv
from app.services.rerank_service import rerank_papers, _get_model
from app.services.pdf_service import get_paper_texts
from app.services.extraction_service import extract_papers

QUERY = "NLG evaluation metrics GPT-4 human alignment"
ARXIV_CANDIDATES = int(os.environ.get("ARXIV_CANDIDATE_COUNT", 10))
TOP_K = int(os.environ.get("TOP_K_PAPERS", 5))

async def run():
    sem = asyncio.Semaphore(5)
    _get_model()

    print(f"\n{'='*60}")
    print(f"  Testing extraction fix — query: '{QUERY}'")
    print('='*60)

    # Clear extraction cache for top papers so we test the real path
    from app.services import cache_service
    from app.services.cache_service import _get_conn

    candidates = await search_arxiv(QUERY, max_results=ARXIV_CANDIDATES)
    print(f"  [1] arXiv: {len(candidates)} candidates")

    top = await rerank_papers(QUERY, candidates, top_k=TOP_K)
    print(f"  [2] Rerank: top {len(top)} papers:")
    for p in top:
        print(f"      • {p.arxiv_id}  {p.title[:70]}")

    # Clear cache for these papers to force re-extraction
    conn = _get_conn()
    for p in top:
        conn.execute("DELETE FROM paper_extractions WHERE arxiv_id=?", (p.arxiv_id,))
    conn.commit()
    print(f"  (cleared extraction cache for {len(top)} papers)")

    texts = await get_paper_texts(top)
    print(f"  [3] Text: {len(texts)} papers")

    print(f"  [4] Extracting (batch + retry)...")
    import time
    t0 = time.perf_counter()
    extracted, errors = await extract_papers(top, texts, semaphore=sem)
    elapsed = time.perf_counter() - t0

    print(f"\n  RESULTS ({elapsed:.1f}s):")
    print(f"  ✅ Extracted: {len(extracted)}/{len(top)}")
    if errors:
        print(f"  ❌ Errors ({len(errors)}):")
        for e in errors:
            print(f"     • {e['arxiv_id']}: {e['error'][:80]}")
    else:
        print(f"  ✅ Zero errors — all papers extracted!")

    print(f"\n  Extracted papers:")
    for ep in extracted:
        print(f"    ✓ {ep.arxiv_id}  {ep.title[:65]}")

if __name__ == "__main__":
    asyncio.run(run())

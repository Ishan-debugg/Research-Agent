"""
Latency benchmark: 3 fresh (non-cached) queries via /search/stream SSE endpoint.
Reports per-stage elapsed times and total pipeline time.
"""

import asyncio
import json
import time
import httpx

BASE_URL = "http://localhost:8000"

QUERIES = [
    "vision transformers for medical image segmentation",
    "federated learning privacy preserving techniques",
    "large language models reasoning chain of thought",
]


async def benchmark_query(client: httpx.AsyncClient, query: str, index: int):
    print(f"\n{'='*60}")
    print(f"Query {index}: {query!r}")
    print(f"{'='*60}")

    url = f"{BASE_URL}/search/stream"
    params = {"query": query}

    stage_times = {}
    total_start = time.perf_counter()
    first_byte_time = None
    result_received = False

    try:
        async with client.stream("GET", url, params=params, timeout=120.0) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                now = time.perf_counter()
                if first_byte_time is None:
                    first_byte_time = now - total_start

                if not line.startswith("data:"):
                    continue

                raw = line[5:].strip()
                if not raw:
                    continue

                try:
                    event_data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                # Detect stage completions
                stage = event_data.get("stage", "")
                elapsed = event_data.get("elapsed")
                message = event_data.get("message", "")

                if elapsed is not None:
                    stage_times[stage] = elapsed
                    print(f"  ✓ [{stage:15s}]  {elapsed:.1f}s  — {message}")

                # Detect final result
                if "data" in event_data and "total_elapsed" in event_data:
                    total_elapsed = event_data["total_elapsed"]
                    from_cache = event_data.get("from_cache", False)
                    result_received = True
                    print(f"\n  {'[CACHED] ' if from_cache else ''}TOTAL: {total_elapsed:.1f}s")
                    print(f"  First byte: {first_byte_time:.2f}s")
                    return {
                        "query": query,
                        "total_elapsed": total_elapsed,
                        "stage_times": stage_times,
                        "first_byte": round(first_byte_time, 2),
                        "from_cache": from_cache,
                    }

                # Detect error
                if "message" in event_data and stage == "" and not result_received:
                    print(f"  ✗ ERROR: {event_data['message']}")
                    return {"query": query, "error": event_data["message"]}

    except Exception as e:
        elapsed = time.perf_counter() - total_start
        print(f"  ✗ EXCEPTION after {elapsed:.1f}s: {e}")
        return {"query": query, "error": str(e), "elapsed": round(elapsed, 1)}

    total = time.perf_counter() - total_start
    return {"query": query, "total_elapsed": round(total, 1), "stage_times": stage_times}


async def main():
    print("\n" + "="*60)
    print("  LATENCY BENCHMARK  —  3 fresh queries")
    print("="*60)

    # First check health
    async with httpx.AsyncClient() as client:
        try:
            health = await client.get(f"{BASE_URL}/health", timeout=5.0)
            h = health.json()
            print(f"\nBackend status: {h.get('status', '?')}")
        except Exception as e:
            print(f"\n⚠ Backend not reachable: {e}")
            print("  Start the backend first: uvicorn app.main:app --reload --port 8000")
            return

    results = []
    # Use a single client for connection reuse across queries
    async with httpx.AsyncClient() as client:
        for i, query in enumerate(QUERIES, start=1):
            result = await benchmark_query(client, query, i)
            results.append(result)
            # Small gap between queries to avoid rate limit (10/min)
            if i < len(QUERIES):
                await asyncio.sleep(2)

    # Summary table
    print(f"\n\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    print(f"  {'Query':<45} {'Total':>8}  {'Cache'}")
    print(f"  {'-'*45} {'-'*8}  {'-'*5}")
    for r in results:
        q = r["query"][:44]
        total = r.get("total_elapsed", "ERR")
        cached = "YES" if r.get("from_cache") else "no"
        err = r.get("error", "")
        if err:
            print(f"  {q:<45} {'ERROR':>8}  {err[:30]}")
        else:
            print(f"  {q:<45} {str(total)+'s':>8}  {cached}")

    totals = [r["total_elapsed"] for r in results if "total_elapsed" in r and not r.get("from_cache")]
    if totals:
        print(f"\n  Avg (non-cached): {sum(totals)/len(totals):.1f}s")
        print(f"  Min: {min(totals):.1f}s  |  Max: {max(totals):.1f}s")
    print()


if __name__ == "__main__":
    asyncio.run(main())

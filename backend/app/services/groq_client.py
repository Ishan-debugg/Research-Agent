"""
groq_client.py — Async Groq API client for fast paper extraction.

Architecture:
  - Uses Groq's OpenAI-compatible REST API (no SDK required, pure httpx)
  - Routes "extraction" task to mixtral-8x7b-32768 (3-4x faster than Gemini flash)
  - Identical public interface to gemini_client.call_gemini() for zero-friction swap
  - Respects asyncio.Semaphore for concurrency cap
  - Retries on 429 with exponential backoff (Groq free: 30 RPM)
  - sanitize_json re-exported so callers need only import groq_client

Public API:
    await call_groq(prompt, semaphore) -> str   (raw JSON string)
    sanitize_json(raw)                -> str   (same as gemini_client)
"""

import asyncio
import logging
import os
import time

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
)

# Re-export sanitize_json so callers don't need a separate import
from app.services.gemini_client import sanitize_json  # noqa: F401

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "mixtral-8x7b-32768")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq free tier: 30 req/min, 14 400 req/day for Mixtral
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "too many requests" in msg


def _call_groq_sync(prompt: str) -> str:
    """
    Synchronous Groq chat-completions call.
    Returns the raw content string (should be JSON).
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment.")

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a research assistant that extracts structured information "
                    "from ML papers. Always respond with a valid JSON array — "
                    "no markdown, no code fences, no commentary. "
                    "If extracting one paper return a single-element array."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
        # NOTE: do NOT use response_format json_object — that forces a single
        # object and breaks batch prompts that expect a JSON array.
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=_TIMEOUT) as client:
        resp = client.post(GROQ_API_URL, json=payload, headers=headers)

    if resp.status_code == 429:
        raise RuntimeError(f"429 Rate limit exceeded: {resp.text}")
    if resp.status_code != 200:
        raise RuntimeError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")

    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if not content or not content.strip():
        raise ValueError("Groq returned empty content.")
    return content


async def call_groq(
    prompt: str,
    semaphore: asyncio.Semaphore | None = None,
) -> str:
    """
    Async Groq call — mirrors gemini_client.call_gemini() signature.
    Wraps the sync HTTP call in a thread-pool executor.
    """
    loop = asyncio.get_running_loop()

    @retry(
        retry=retry_if_exception(_is_rate_limit),
        wait=wait_exponential_jitter(initial=2, max=30, jitter=3),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _attempt() -> str:
        return await loop.run_in_executor(None, _call_groq_sync, prompt)

    class _null_ctx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    async with (semaphore if semaphore else _null_ctx()):
        t0 = time.perf_counter()
        try:
            result = await _attempt()
            elapsed = time.perf_counter() - t0
            logger.info("[groq] extraction  model=%-28s  %.1fs", GROQ_MODEL, elapsed)
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.error("[groq] Failed after %.1fs: %s", elapsed, exc)
            raise

"""
groq_client.py — Async Groq API client for fast paper extraction.

Architecture:
  - Uses Groq's OpenAI-compatible REST API (no SDK required, pure httpx)
  - Routes "extraction" task to llama-3.1-8b-instant (fastest Groq model)
  - Native async httpx.AsyncClient — no thread-pool wrapping, true async I/O
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
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Groq free tier: 30 req/min, 14 400 req/day
_TIMEOUT = httpx.Timeout(60.0, connect=10.0)

# Shared async client — created once per process lifetime, reused across calls.
# AsyncClient keeps a connection pool open so subsequent requests skip TCP handshake.
_async_client: httpx.AsyncClient | None = None


def _get_async_client() -> httpx.AsyncClient:
    """Return (or lazily create) the shared async HTTP client."""
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(timeout=_TIMEOUT)
    return _async_client


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "rate_limit" in msg or "too many requests" in msg


async def _call_groq_async(prompt: str, system_message: str | None = None) -> str:
    """
    Native async Groq chat-completions call via httpx.AsyncClient.
    No thread-pool wrapping — true async I/O keeps the event loop free.
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not set in environment.")

    default_system = (
        "You are a research assistant that extracts structured information "
        "from ML papers. Always respond with a valid JSON array — "
        "no markdown, no code fences, no commentary. "
        "If extracting one paper return a single-element array."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_message or default_system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    client = _get_async_client()
    resp = await client.post(GROQ_API_URL, json=payload, headers=headers)

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
    system_message: str | None = None,
    model_override: str | None = None,
) -> str:
    """
    Native async Groq call — no thread-pool executor.
    Uses a shared httpx.AsyncClient with a persistent connection pool.

    Args:
        prompt:          The user prompt string.
        semaphore:       asyncio.Semaphore for concurrency cap (optional).
        system_message:  Custom system prompt (defaults to extraction assistant).
        model_override:  Override GROQ_MODEL for this call (e.g. graph synthesis).
    """
    target_model = model_override or GROQ_MODEL

    @retry(
        retry=retry_if_exception(_is_rate_limit),
        wait=wait_exponential_jitter(initial=1, max=15, jitter=2),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    async def _attempt() -> str:
        return await _call_groq_async(prompt, system_message)

    class _null_ctx:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): pass

    async with (semaphore if semaphore else _null_ctx()):
        t0 = time.perf_counter()
        try:
            result = await _attempt()
            elapsed = time.perf_counter() - t0
            logger.info("[groq] %-12s  model=%-28s  %.1fs", "graph" if model_override else "extraction", target_model, elapsed)
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            logger.error("[groq] Failed after %.1fs: %s", elapsed, exc)
            raise

"""
gemini_client.py — Central Gemini model router with fallback and concurrency control.

Architecture:
  Two model tiers are configured via environment variables:
    EXTRACTION_MODEL  (default: gemini-2.5-flash-lite)  — cheap, fast, deterministic
    SYNTHESIS_MODEL   (default: gemini-2.5-flash)        — smarter, for graph/summary

  Task routing:
    "extraction" → EXTRACTION_MODEL  (temperature=0.0, top_k=1, top_p=1.0)
    "synthesis"  → SYNTHESIS_MODEL   (temperature=0.2, top_k=40, top_p=0.9)

  Fallback strategy:
    On HTTP 429 (ResourceExhausted) the router automatically retries with
    exponential backoff + jitter via tenacity. If the primary model is exhausted,
    it falls back to the alternate model in the tier.

  Concurrency:
    All callers pass an asyncio.Semaphore (created in main.py, default max=5).
    This caps simultaneous Gemini requests to avoid hitting RPM limits.

  Logging:
    Every call logs: task type, model used, latency, and whether a fallback
    occurred. This makes performance bottlenecks immediately visible in the
    uvicorn terminal.

Public API (single function):
    await call_gemini(task_type, prompt, semaphore) -> str
"""

import asyncio
import logging
import os
import time

import google.generativeai as genai
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model configuration — change models here or via .env without touching callers
# ---------------------------------------------------------------------------

EXTRACTION_MODEL = os.environ.get("EXTRACTION_MODEL", "gemini-2.5-flash-lite")
SYNTHESIS_MODEL  = os.environ.get("SYNTHESIS_MODEL",  "gemini-2.5-flash")

# Kept for backward-compat with techmatch_service which imported MODEL_NAME
MODEL_NAME = EXTRACTION_MODEL

_TASK_CONFIG: dict[str, dict] = {
    "extraction": {
        "primary":          EXTRACTION_MODEL,
        "fallback":         SYNTHESIS_MODEL,
        # Temperature 0.0 → maximally deterministic; eliminates hallucinated metrics
        "temperature":      0.0,
        "top_p":            1.0,     # No nucleus sampling at T=0 (greedy)
        "top_k":            1,       # Greedy decoding — single most likely token
        "max_output_tokens": 4096,   # Extraction JSON for 5 papers ≈ 3-4k tokens
    },
    "synthesis": {
        "primary":          SYNTHESIS_MODEL,
        "fallback":         EXTRACTION_MODEL,
        # Small temperature for creative cross-paper relationships
        "temperature":      0.2,
        "top_p":            0.9,     # Tighter nucleus sampling
        "top_k":            40,      # Standard diverse decoding
        "max_output_tokens": 4096,   # Graph JSON is typically ~1-3k tokens
    },
}


# ---------------------------------------------------------------------------
# Internal retry-aware call (synchronous, run in executor)
# ---------------------------------------------------------------------------

def _is_rate_limit(exc: Exception) -> bool:
    """Detect Google quota errors by inspecting the exception message."""
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _call_model_sync(model_name: str, prompt: str, temperature: float,
                     top_p: float, top_k: int, max_output_tokens: int) -> str:
    """Make a single synchronous Gemini call and return the text response."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": temperature,
            "top_p": top_p,
            "top_k": top_k,
            "max_output_tokens": max_output_tokens,
        },
        request_options={"timeout": 90},
    )
    return response.text


# ---------------------------------------------------------------------------
# Public async interface
# ---------------------------------------------------------------------------

async def call_gemini(
    task_type: str,
    prompt: str,
    semaphore: asyncio.Semaphore | None = None,
) -> str:
    """
    Async Gemini call with:
      - Model routing by task_type ("extraction" | "synthesis")
      - Concurrency control via semaphore
      - Automatic fallback on rate-limit errors with exponential backoff + jitter
      - Structured latency logging

    Args:
        task_type:  "extraction" or "synthesis"
        prompt:     The full prompt string to send
        semaphore:  asyncio.Semaphore for concurrency cap (pass None to skip)

    Returns:
        Raw JSON string from Gemini
    """
    cfg = _TASK_CONFIG.get(task_type, _TASK_CONFIG["extraction"])
    primary_model    = cfg["primary"]
    fallback_model   = cfg["fallback"]
    temperature      = cfg["temperature"]
    top_p            = cfg["top_p"]
    top_k            = cfg["top_k"]
    max_output_tokens = cfg["max_output_tokens"]

    loop = asyncio.get_running_loop()

    async def _run_with_model(model_name: str) -> str:
        """Run the synchronous Gemini call in a thread pool."""
        return await loop.run_in_executor(
            None, _call_model_sync, model_name, prompt,
            temperature, top_p, top_k, max_output_tokens,
        )

    # Tenacity retry wrapper for transient rate-limit errors
    @retry(
        retry=retry_if_exception(_is_rate_limit),
        wait=wait_exponential_jitter(initial=1, max=30, jitter=2),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _call_primary() -> str:
        return await _run_with_model(primary_model)

    async with (semaphore if semaphore else _null_context()):
        t0 = time.perf_counter()
        try:
            result = await _call_primary()
            elapsed = time.perf_counter() - t0
            logger.info(
                "[gemini] %-12s  model=%-30s  %.1fs",
                task_type, primary_model, elapsed,
            )
            return result
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning(
                    "[gemini] RATE LIMIT on %s after retries — falling back to %s",
                    primary_model, fallback_model,
                )
                t1 = time.perf_counter()
                try:
                    result = await _run_with_model(fallback_model)
                    elapsed = time.perf_counter() - t1
                    logger.info(
                        "[gemini] %-12s  model=%-30s  %.1fs  [FALLBACK]",
                        task_type, fallback_model, elapsed,
                    )
                    return result
                except Exception as inner_exc:
                    logger.error("[gemini] Fallback also failed: %s", inner_exc)
                    raise inner_exc from exc
            else:
                logger.error("[gemini] %s error on %s: %s", task_type, primary_model, exc)
                raise


class _null_context:
    """Async no-op context manager used when no semaphore is provided."""
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        pass

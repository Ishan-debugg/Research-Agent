"""
gemini_client.py — Central Gemini model router with fallback and concurrency control.

Architecture:
  Two model tiers are configured via environment variables:
    EXTRACTION_MODEL  (default: gemini-2.5-flash-lite)  — cheap, fast, deterministic
    SYNTHESIS_MODEL   (default: gemini-2.5-flash)        — smarter, for graph/summary

  Task routing:
    "extraction" → EXTRACTION_MODEL  (temperature=0.0)
    "synthesis"  → SYNTHESIS_MODEL   (temperature=0.2)

  Fallback strategy:
    On HTTP 429 (ResourceExhausted) the router automatically retries the
    *other* model in the tier with exponential backoff. This prevents a
    single rate-limited model from stalling the entire pipeline.

  Concurrency:
    All callers pass an asyncio.Semaphore (created in main.py, default max=3).
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
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
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
        "primary":     EXTRACTION_MODEL,
        "fallback":    SYNTHESIS_MODEL,
        # Temperature 0.0 → maximally deterministic; eliminates hallucinated metrics
        "temperature": 0.0,
    },
    "synthesis": {
        "primary":     SYNTHESIS_MODEL,
        "fallback":    EXTRACTION_MODEL,
        # Small temperature for creative cross-paper relationships
        "temperature": 0.2,
    },
}


# ---------------------------------------------------------------------------
# Internal retry-aware call (synchronous, run in executor)
# ---------------------------------------------------------------------------

def _is_rate_limit(exc: Exception) -> bool:
    """Detect Google quota errors by inspecting the exception message."""
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "quota" in msg


def _call_model_sync(model_name: str, prompt: str, temperature: float) -> str:
    """Make a single synchronous Gemini call and return the text response."""
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": temperature,
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
      - Automatic fallback on rate-limit errors
      - Structured latency logging

    Args:
        task_type:  "extraction" or "synthesis"
        prompt:     The full prompt string to send
        semaphore:  asyncio.Semaphore for concurrency cap (pass None to skip)

    Returns:
        Raw JSON string from Gemini
    """
    cfg = _TASK_CONFIG.get(task_type, _TASK_CONFIG["extraction"])
    primary_model  = cfg["primary"]
    fallback_model = cfg["fallback"]
    temperature    = cfg["temperature"]

    loop = asyncio.get_event_loop()

    async def _run_with_model(model_name: str) -> str:
        """Run the synchronous Gemini call in a thread pool."""
        return await loop.run_in_executor(
            None, _call_model_sync, model_name, prompt, temperature
        )

    acquire = semaphore.acquire() if semaphore else asyncio.sleep(0)

    async with (semaphore if semaphore else _null_context()):
        t0 = time.perf_counter()
        try:
            result = await _run_with_model(primary_model)
            elapsed = time.perf_counter() - t0
            logger.info(
                "[gemini] %-12s  model=%-30s  %.1fs",
                task_type, primary_model, elapsed,
            )
            return result
        except Exception as exc:
            if _is_rate_limit(exc):
                logger.warning(
                    "[gemini] RATE LIMIT on %s — falling back to %s",
                    primary_model, fallback_model,
                )
                # Exponential back-off before hitting fallback
                await asyncio.sleep(2)
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

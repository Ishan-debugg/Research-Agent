"""
cache_service.py — Persistent SQLite cache for the research pipeline.

Architecture decision: Redis is not available in the local environment,
so we use SQLite (Python stdlib, zero extra dependencies). The three
tables map directly to the three expensive pipeline stages we want to
short-circuit on repeated queries:

  paper_texts       → Stage 3 output  (PDF extraction)
  paper_extractions → Stage 4 output  (Gemini structured extraction)
  graph_cache       → Stage 5 output  (Gemini knowledge graph)

Cache keys:
  paper_texts / paper_extractions : arxiv_id  (e.g. "2310.01558v2")
  graph_cache                     : SHA-256 of the sorted arxiv_id list

Thread safety: a single threading.Lock protects all writes so uvicorn's
threaded worker pool never races on the same db connection.

Future migration to Redis: replace the _get/set helpers below with
redis-py calls — the public interface (function signatures) stays identical.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

_CACHE_DIR = os.environ.get("CACHE_DIR", "./cache")
_DB_PATH = os.path.join(_CACHE_DIR, "papers.db")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def _get_conn() -> sqlite3.Connection:
    """Return (and lazily initialise) the shared SQLite connection."""
    global _conn
    if _conn is None:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _create_tables(_conn)
        logger.info("[cache] SQLite cache initialised at %s", _DB_PATH)
    return _conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS paper_texts (
            arxiv_id    TEXT PRIMARY KEY,
            text        TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS paper_extractions (
            arxiv_id    TEXT PRIMARY KEY,
            data_json   TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS graph_cache (
            query_hash  TEXT PRIMARY KEY,
            data_json   TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
    """)
    conn.commit()


# ---------------------------------------------------------------------------
# Paper text (Stage 3)
# ---------------------------------------------------------------------------

def get_paper_text(arxiv_id: str) -> str | None:
    """Return cached PDF text for *arxiv_id*, or None on a miss."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT text FROM paper_texts WHERE arxiv_id = ?", (arxiv_id,)
    ).fetchone()
    if row:
        logger.info("[cache] TEXT HIT  — %s", arxiv_id)
        return row["text"]
    logger.info("[cache] TEXT MISS — %s", arxiv_id)
    return None


def set_paper_text(arxiv_id: str, text: str) -> None:
    """Persist extracted PDF text for *arxiv_id*."""
    with _lock:
        _get_conn().execute(
            "INSERT OR REPLACE INTO paper_texts (arxiv_id, text, created_at) VALUES (?, ?, ?)",
            (arxiv_id, text, datetime.utcnow().isoformat()),
        )
        _get_conn().commit()
    logger.info("[cache] TEXT SET  — %s (%d chars)", arxiv_id, len(text))


# ---------------------------------------------------------------------------
# Structured extraction (Stage 4)
# ---------------------------------------------------------------------------

def get_extraction(arxiv_id: str) -> dict | None:
    """Return cached ExtractedPaper dict for *arxiv_id*, or None on a miss."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT data_json FROM paper_extractions WHERE arxiv_id = ?", (arxiv_id,)
    ).fetchone()
    if row:
        logger.info("[cache] EXTRACTION HIT  — %s", arxiv_id)
        return json.loads(row["data_json"])
    logger.info("[cache] EXTRACTION MISS — %s", arxiv_id)
    return None


def set_extraction(arxiv_id: str, data: dict) -> None:
    """Persist structured extraction dict for *arxiv_id*."""
    with _lock:
        _get_conn().execute(
            "INSERT OR REPLACE INTO paper_extractions (arxiv_id, data_json, created_at) VALUES (?, ?, ?)",
            (arxiv_id, json.dumps(data), datetime.utcnow().isoformat()),
        )
        _get_conn().commit()
    logger.info("[cache] EXTRACTION SET  — %s", arxiv_id)


# ---------------------------------------------------------------------------
# Knowledge graph (Stage 5)
# ---------------------------------------------------------------------------

def get_graph(query_hash: str) -> dict | None:
    """Return cached KnowledgeGraph dict for *query_hash*, or None on a miss."""
    conn = _get_conn()
    row = conn.execute(
        "SELECT data_json FROM graph_cache WHERE query_hash = ?", (query_hash,)
    ).fetchone()
    if row:
        logger.info("[cache] GRAPH HIT  — hash=%s", query_hash[:12])
        return json.loads(row["data_json"])
    logger.info("[cache] GRAPH MISS — hash=%s", query_hash[:12])
    return None


def set_graph(query_hash: str, data: dict) -> None:
    """Persist KnowledgeGraph dict for *query_hash*."""
    with _lock:
        _get_conn().execute(
            "INSERT OR REPLACE INTO graph_cache (query_hash, data_json, created_at) VALUES (?, ?, ?)",
            (query_hash, json.dumps(data), datetime.utcnow().isoformat()),
        )
        _get_conn().commit()
    logger.info("[cache] GRAPH SET  — hash=%s", query_hash[:12])

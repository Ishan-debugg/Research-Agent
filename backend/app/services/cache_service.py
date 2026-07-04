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

TTL support: every table has a created_at timestamp. Get helpers accept
a ttl_hours parameter; entries older than TTL are treated as misses
and lazily purged.

WAL mode: journal_mode=WAL enables concurrent readers alongside a
single writer, eliminating read-side lock contention.

Future migration to Redis: replace the _get/set helpers below with
redis-py calls — the public interface (function signatures) stays identical.
"""

import json
import logging
import os
import sqlite3
import threading
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_CACHE_DIR = os.environ.get("CACHE_DIR", "./cache")
_DB_PATH = os.path.join(_CACHE_DIR, "papers.db")
_lock = threading.Lock()
_conn: sqlite3.Connection | None = None

# Default TTLs (hours) — override via environment variables
PAPER_TEXT_TTL_HOURS = int(os.environ.get("PAPER_TEXT_TTL_HOURS", 168))        # 7 days
PAPER_EXTRACTION_TTL_HOURS = int(os.environ.get("EXTRACTION_TTL_HOURS", 168)) # 7 days
GRAPH_TTL_HOURS = int(os.environ.get("GRAPH_TTL_HOURS", 72))                  # 3 days (was 24h)


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    """Return (and lazily initialise) the shared SQLite connection."""
    global _conn
    if _conn is None:
        os.makedirs(_CACHE_DIR, exist_ok=True)
        _conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        # WAL mode: allows concurrent reads without blocking on write lock
        _conn.execute("PRAGMA journal_mode=WAL")
        # Wait up to 5s if the DB is locked instead of immediately failing
        _conn.execute("PRAGMA busy_timeout=5000")
        _create_tables(_conn)
        logger.info("[cache] SQLite cache initialised at %s (WAL mode)", _DB_PATH)
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


def _is_expired(created_at_iso: str, ttl_hours: int) -> bool:
    """Check if a cache entry has exceeded its TTL."""
    try:
        created = datetime.fromisoformat(created_at_iso)
        return datetime.utcnow() - created > timedelta(hours=ttl_hours)
    except (ValueError, TypeError):
        # If the timestamp is malformed, treat as expired
        return True


def _purge_expired(table: str, key_col: str, key_val: str) -> None:
    """Lazily delete an expired entry (best-effort, non-blocking)."""
    # Allowlist to prevent SQL injection via table/column names
    _VALID_TABLES = {"paper_texts", "paper_extractions", "graph_cache"}
    _VALID_COLS = {"arxiv_id", "query_hash"}
    if table not in _VALID_TABLES or key_col not in _VALID_COLS:
        logger.error("[cache] Invalid table/column in purge: %s/%s", table, key_col)
        return
    try:
        with _lock:
            _get_conn().execute(
                f"DELETE FROM {table} WHERE {key_col} = ?", (key_val,)  # noqa: S608
            )
            _get_conn().commit()
        logger.info("[cache] PURGED expired entry from %s — %s", table, key_val)
    except Exception as e:
        logger.warning("[cache] Failed to purge %s/%s: %s", table, key_val, e)


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

def close() -> None:
    """Close the SQLite connection cleanly. Called on app shutdown."""
    global _conn
    if _conn is not None:
        try:
            _conn.close()
            logger.info("[cache] SQLite connection closed.")
        except Exception as e:
            logger.warning("[cache] Error closing SQLite: %s", e)
        finally:
            _conn = None


# ---------------------------------------------------------------------------
# Bulk pruner — removes ALL expired rows across all tables in one pass.
# Call on startup and/or schedule periodically.
# ---------------------------------------------------------------------------

def prune_expired_entries() -> dict:
    """
    Delete all entries that have exceeded their TTL from every table.
    Returns counts of deleted rows per table for observability.
    """
    now = datetime.utcnow()
    deleted = {}
    specs = [
        ("paper_texts",       "arxiv_id",   PAPER_TEXT_TTL_HOURS),
        ("paper_extractions", "arxiv_id",   PAPER_EXTRACTION_TTL_HOURS),
        ("graph_cache",       "query_hash", GRAPH_TTL_HOURS),
    ]
    with _lock:
        conn = _get_conn()
        for table, _, ttl in specs:
            cutoff = (now - timedelta(hours=ttl)).isoformat()
            cur = conn.execute(
                f"DELETE FROM {table} WHERE created_at < ?",  # noqa: S608
                (cutoff,)
            )
            deleted[table] = cur.rowcount
        conn.commit()
    total = sum(deleted.values())
    if total:
        logger.info("[cache] Pruned %d expired entries: %s", total, deleted)
    return deleted


def cache_stats() -> dict:
    """Return row counts and oldest/newest entry per table for health checks."""
    conn = _get_conn()
    stats = {}
    for table in ("paper_texts", "paper_extractions", "graph_cache"):
        try:
            row = conn.execute(
                f"SELECT COUNT(*) as cnt, MIN(created_at) as oldest, MAX(created_at) as newest FROM {table}"  # noqa: S608
            ).fetchone()
            stats[table] = {
                "count": row["cnt"],
                "oldest": row["oldest"],
                "newest": row["newest"],
            }
        except Exception as e:
            stats[table] = {"error": str(e)}
    return stats


def start_background_pruner(interval_hours: int = 6) -> None:
    """Start a daemon thread that prunes expired cache entries every N hours."""
    import threading

    def _loop():
        import time as _time
        while True:
            _time.sleep(interval_hours * 3600)
            try:
                prune_expired_entries()
            except Exception as e:
                logger.warning("[cache] Background pruner error: %s", e)

    t = threading.Thread(target=_loop, daemon=True, name="cache-pruner")
    t.start()
    logger.info("[cache] Background pruner started (interval=%dh)", interval_hours)


# ---------------------------------------------------------------------------
# Paper text (Stage 3) — TTL default: 7 days
# ---------------------------------------------------------------------------

def get_paper_text(arxiv_id: str, ttl_hours: int | None = None) -> str | None:
    """Return cached PDF text for *arxiv_id*, or None on a miss / expired."""
    if ttl_hours is None:
        ttl_hours = PAPER_TEXT_TTL_HOURS
    conn = _get_conn()
    row = conn.execute(
        "SELECT text, created_at FROM paper_texts WHERE arxiv_id = ?", (arxiv_id,)
    ).fetchone()
    if row:
        if _is_expired(row["created_at"], ttl_hours):
            logger.info("[cache] TEXT EXPIRED — %s (age > %dh)", arxiv_id, ttl_hours)
            _purge_expired("paper_texts", "arxiv_id", arxiv_id)
            return None
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
# Structured extraction (Stage 4) — TTL default: 7 days
# ---------------------------------------------------------------------------

def get_extraction(arxiv_id: str, ttl_hours: int | None = None) -> dict | None:
    """Return cached ExtractedPaper dict for *arxiv_id*, or None on a miss / expired."""
    if ttl_hours is None:
        ttl_hours = PAPER_EXTRACTION_TTL_HOURS
    conn = _get_conn()
    row = conn.execute(
        "SELECT data_json, created_at FROM paper_extractions WHERE arxiv_id = ?", (arxiv_id,)
    ).fetchone()
    if row:
        if _is_expired(row["created_at"], ttl_hours):
            logger.info("[cache] EXTRACTION EXPIRED — %s (age > %dh)", arxiv_id, ttl_hours)
            _purge_expired("paper_extractions", "arxiv_id", arxiv_id)
            return None
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
# Knowledge graph (Stage 5) — TTL default: 24 hours
# ---------------------------------------------------------------------------

def get_graph(query_hash: str, ttl_hours: int | None = None) -> dict | None:
    """Return cached KnowledgeGraph dict for *query_hash*, or None on a miss / expired."""
    if ttl_hours is None:
        ttl_hours = GRAPH_TTL_HOURS
    conn = _get_conn()
    row = conn.execute(
        "SELECT data_json, created_at FROM graph_cache WHERE query_hash = ?", (query_hash,)
    ).fetchone()
    if row:
        if _is_expired(row["created_at"], ttl_hours):
            logger.info("[cache] GRAPH EXPIRED — hash=%s (age > %dh)", query_hash[:12], ttl_hours)
            _purge_expired("graph_cache", "query_hash", query_hash)
            return None
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

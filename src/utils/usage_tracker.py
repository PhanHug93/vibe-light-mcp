"""
Usage Tracker — Daily Analytics & Satisfaction Scoring.

Tracks MCP tool calls to produce daily reports:
  - Which tech stacks were queried and how often.
  - Satisfaction score based on query diversity
    (repeated queries / context re-reads = low satisfaction).

Architecture: Pure logic — no MCP dependency.
``main.py`` imports and wraps with ``@mcp.tool()``.

Storage: JSON files in ``./.usage_logs/YYYY-MM-DD.json``.

Performance notes:
  - **Buffered writes**: ``record_tool_call`` appends to an in-memory
    buffer and flushes to disk only when the buffer reaches
    ``_FLUSH_SIZE`` entries.  An ``atexit`` hook guarantees any
    remaining entries are written on shutdown.
  - **Bounded similarity**: Satisfaction scoring limits pairwise
    comparisons to a sliding window (``_SIMILARITY_WINDOW``) and
    short-circuits on exact matches and length mismatches.
"""

from __future__ import annotations

import atexit
import contextlib
import json
import logging
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from src.config import (
    USAGE_LOG_DIR,
    SIMILARITY_THRESHOLD,
    SIMILARITY_WINDOW,
    FLUSH_SIZE,
)

logger = logging.getLogger(__name__)

_LOG_DIR: Path = USAGE_LOG_DIR
_SIMILARITY_THRESHOLD: float = SIMILARITY_THRESHOLD
_SIMILARITY_WINDOW: int = SIMILARITY_WINDOW
_FLUSH_SIZE: int = FLUSH_SIZE


# ---------------------------------------------------------------------------
# Cross-platform file lock (Unix: fcntl, Windows: msvcrt)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _file_lock(f):
    """Acquire an exclusive file lock, cross-platform.

    - Unix/macOS: ``fcntl.flock``
    - Windows: ``msvcrt.locking``
    - Fallback: no-op (log warning once)
    """
    if sys.platform == "win32":
        import msvcrt
        # msvcrt.locking locks 1 byte at current position
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            try:
                f.seek(0)
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
    else:
        try:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        except ImportError:
            logger.warning("fcntl not available — file locking disabled.")
            yield


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD (local timezone)."""
    return datetime.now().strftime("%Y-%m-%d")


def _log_path(date: str | None = None) -> Path:
    """Return the log file path for a given date (default: today)."""
    return _LOG_DIR / f"{date or _today_str()}.jsonl"


def _load_log(date: str | None = None) -> list[dict]:
    """Load log entries (supports both .jsonl and legacy .json)."""
    jsonl_path = _LOG_DIR / f"{date or _today_str()}.jsonl"
    json_path = _LOG_DIR / f"{date or _today_str()}.json"

    entries: list[dict] = []

    # Read JSONL (primary format)
    if jsonl_path.exists():
        try:
            for line in jsonl_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read %s: %s", jsonl_path, exc)

    # Backward compat: also read legacy .json if exists
    if json_path.exists():
        try:
            legacy = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(legacy, list):
                entries.extend(legacy)
        except (json.JSONDecodeError, OSError):
            pass

    return entries


def _append_jsonl(entries: list[dict], date: str | None = None) -> None:
    """Append entries to JSONL file with cross-platform file lock."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _log_path(date)
    lines = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    try:
        with open(path, "a", encoding="utf-8") as f:
            with _file_lock(f):
                f.write(lines)
    except OSError as exc:
        logger.warning("Failed to write usage log: %s", exc)


def _is_similar(a: str, b: str, threshold: float = _SIMILARITY_THRESHOLD) -> bool:
    """Check if two strings are similar above threshold (0–1).

    Optimisations over the original:
    - Exact match → True immediately (O(1))
    - Length mismatch > 2× → False immediately (skip SequenceMatcher)
    """
    if not a or not b:
        return False
    # Normalise once (callers should pre-normalise when possible)
    a_lower = a.lower()
    b_lower = b.lower()
    # Exact match shortcut
    if a_lower == b_lower:
        return True
    # Length ratio shortcut — very different lengths can't be similar
    len_a, len_b = len(a_lower), len(b_lower)
    if len_a > 2 * len_b or len_b > 2 * len_a:
        return False
    return SequenceMatcher(None, a_lower, b_lower).ratio() >= threshold


# ---------------------------------------------------------------------------
# Buffered write for record_tool_call (Fix #3)
# ---------------------------------------------------------------------------

_buffer: list[dict] = []
_buffer_lock = threading.Lock()


def _flush_buffer() -> None:
    """Flush buffered entries to disk (thread-safe, append-only JSONL)."""
    global _buffer  # noqa: PLW0603
    with _buffer_lock:
        if not _buffer:
            return
        to_flush = list(_buffer)
        _buffer = []

    _append_jsonl(to_flush)
    logger.debug("Flushed %d usage entries to disk.", len(to_flush))


# Guarantee flush on interpreter shutdown.
atexit.register(_flush_buffer)


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------


def record_tool_call(
    tool_name: str,
    stack: str | None = None,
    query: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Record a tool call for analytics.

    Entries are buffered in memory and flushed to disk when the buffer
    reaches ``_FLUSH_SIZE`` or at interpreter shutdown (``atexit``).

    Args:
        tool_name: Name of the MCP tool called.
        stack: Detected tech stack (if applicable).
        query: The user's query/input text (for similarity analysis).
        metadata: Any extra info to store.
    """
    entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool_name,
    }
    if stack:
        entry["stack"] = stack
    if query:
        entry["query"] = query[:500]  # truncate long queries
    if metadata:
        entry["metadata"] = metadata

    with _buffer_lock:
        _buffer.append(entry)
        should_flush = len(_buffer) >= _FLUSH_SIZE

    if should_flush:
        _flush_buffer()


def get_daily_stats(date: str | None = None) -> str:
    """Compute daily usage statistics and satisfaction score.

    Satisfaction score (0–100) is based on:
      - Higher = more diverse queries (user exploring new knowledge)
      - Lower = many repeated/similar queries (user re-requesting same info)

    Performance: Similarity comparisons are bounded to a sliding window
    of ``_SIMILARITY_WINDOW`` previous queries (O(n×k) instead of O(n²)).

    Args:
        date: Date string YYYY-MM-DD (default: today).

    Returns:
        JSON string with daily report.
    """
    # Flush buffer first so stats include recent calls
    _flush_buffer()

    target_date = date or _today_str()
    entries = _load_log(target_date)

    if not entries:
        return json.dumps(
            {
                "status": "no_data",
                "date": target_date,
                "message": "No tool calls recorded for this date.",
            },
            indent=2,
            ensure_ascii=False,
        )

    # --- Tool call counts ---
    tool_counts: Counter = Counter(e["tool"] for e in entries)

    # --- Stack usage ---
    stack_counts: Counter = Counter(
        e["stack"] for e in entries if e.get("stack")
    )

    # --- Satisfaction scoring (bounded window) ---
    queries: list[str] = [e["query"] for e in entries if e.get("query")]
    total_queries = len(queries)
    repeated_count = 0

    if total_queries >= 2:
        # Pre-normalise for faster comparison
        normalised = [q.lower() for q in queries]
        # Exact-match dedup set
        seen_exact: set[str] = set()

        for i in range(len(normalised)):
            q = normalised[i]
            # Exact match shortcut
            if q in seen_exact:
                repeated_count += 1
                continue
            seen_exact.add(q)

            # Fuzzy match within bounded window (last _SIMILARITY_WINDOW)
            window_start = max(0, i - _SIMILARITY_WINDOW)
            for j in range(window_start, i):
                if _is_similar(normalised[i], normalised[j]):
                    repeated_count += 1
                    break  # count once per query

    # Score: 100 = all unique, 0 = all repeated
    if total_queries == 0:
        satisfaction = 100
    elif total_queries == 1:
        satisfaction = 100
    else:
        unique_ratio = 1.0 - (repeated_count / total_queries)
        satisfaction = round(unique_ratio * 100)

    # --- Satisfaction label ---
    if satisfaction >= 80:
        label = "🟢 Excellent — Knowledge base is serving well"
    elif satisfaction >= 60:
        label = "🟡 Good — Some repeated queries detected"
    elif satisfaction >= 40:
        label = "🟠 Fair — Consider enriching rules/skills"
    else:
        label = "🔴 Low — Users re-requesting same context frequently"

    # --- Time range ---
    timestamps = [e["timestamp"] for e in entries]
    first_call = min(timestamps)
    last_call = max(timestamps)

    return json.dumps(
        {
            "status": "success",
            "date": target_date,
            "summary": {
                "total_calls": len(entries),
                "first_call": first_call,
                "last_call": last_call,
            },
            "tool_usage": dict(tool_counts.most_common()),
            "stack_usage": dict(stack_counts.most_common()),
            "satisfaction": {
                "score": satisfaction,
                "label": label,
                "total_queries": total_queries,
                "repeated_queries": repeated_count,
                "unique_queries": total_queries - repeated_count,
            },
        },
        indent=2,
        ensure_ascii=False,
    )

"""
Usage Tracker — Daily Analytics & Satisfaction Scoring.

Tracks MCP tool calls to produce daily reports:
  - Which tech stacks were queried and how often.
  - Satisfaction score based on query diversity
    (repeated queries / context re-reads = low satisfaction).

Architecture: Pure logic — no MCP dependency.
``main.py`` imports and wraps with ``@mcp.tool()``.

Storage: JSON files in ``./.usage_logs/YYYY-MM-DD.json``.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_BASE_DIR: Path = Path(__file__).resolve().parent
_LOG_DIR: Path = _BASE_DIR / ".usage_logs"
_SIMILARITY_THRESHOLD: float = 0.7  # queries ≥70% similar → "repeated"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD (local timezone)."""
    return datetime.now().strftime("%Y-%m-%d")


def _log_path(date: str | None = None) -> Path:
    """Return the log file path for a given date (default: today)."""
    return _LOG_DIR / f"{date or _today_str()}.json"


def _load_log(date: str | None = None) -> list[dict]:
    """Load today's log entries."""
    path = _log_path(date)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_log(entries: list[dict], date: str | None = None) -> None:
    """Persist log entries to disk."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = _log_path(date)
    path.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _is_similar(a: str, b: str, threshold: float = _SIMILARITY_THRESHOLD) -> bool:
    """Check if two strings are similar above threshold (0–1)."""
    if not a or not b:
        return False
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


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

    Args:
        tool_name: Name of the MCP tool called.
        stack: Detected tech stack (if applicable).
        query: The user's query/input text (for similarity analysis).
        metadata: Any extra info to store.
    """
    entries = _load_log()
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

    entries.append(entry)
    _save_log(entries)


def get_daily_stats(date: str | None = None) -> str:
    """Compute daily usage statistics and satisfaction score.

    Satisfaction score (0–100) is based on:
      - Higher = more diverse queries (user exploring new knowledge)
      - Lower = many repeated/similar queries (user re-requesting same info)

    Args:
        date: Date string YYYY-MM-DD (default: today).

    Returns:
        JSON string with daily report.
    """
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

    # --- Satisfaction scoring ---
    queries: list[str] = [e["query"] for e in entries if e.get("query")]
    total_queries = len(queries)
    repeated_count = 0

    if total_queries >= 2:
        # Compare each query with all previous queries
        for i in range(1, len(queries)):
            for j in range(i):
                if _is_similar(queries[i], queries[j]):
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

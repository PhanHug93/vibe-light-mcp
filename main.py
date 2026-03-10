"""
TechStackLocalMCP — Entry Point.

Boots a FastMCP server exposing tools for Hybrid RAG (L1/L2 Memory):

  1. ``analyze_workspace``      — detect tech stack → return rules & skills
  2. ``store_working_context``  — store to L1 (per-workspace short-term)
  3. ``store_knowledge``        — store to L2 (global long-term)
  4. ``search_memory``          — federated search L1+L2 with re-ranking
  5. ``cleanup_workspace``      — garbage-collect old L1 records
  6. ``memory_stats``           — L1/L2 collection statistics
  7. ``run_terminal_command``   — sandboxed shell execution
  8. ``sync_knowledge``         — git-backed knowledge sync
  9. ``server_health``          — report server status & resource usage
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from context_engine import (
    compress_and_store,
    query_memory,
    cleanup_l1,
    get_memory_stats,
)
from execution_engine import execute_terminal_command
from knowledge_updater import sync_knowledge_from_git

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TechStackLocalMCP")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_BASE_DIR: Path = Path(__file__).resolve().parent
_TECH_STACKS_DIR: Path = _BASE_DIR / "tech_stacks"

# Ordered by specificity: most specific first.
_STACK_SIGNATURES: list[tuple[str, str]] = [
    ("settings.gradle.kts", "kmp"),
    ("build.gradle.kts",    "android_kotlin"),
    ("build.gradle",        "android_kotlin"),
    ("pubspec.yaml",        "flutter_dart"),
    ("package.json",        "vue_js"),
]

_SEARCH_DEPTH: int = 1  # root + one level deep


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_stack(project_path: Path) -> str | None:
    """Scan *project_path* for signature files and return the stack key."""
    for depth in range(_SEARCH_DEPTH + 1):
        search_dirs: list[Path] = (
            [project_path] if depth == 0
            else [d for d in project_path.iterdir() if d.is_dir()]
        )
        for directory in search_dirs:
            for signature, stack in _STACK_SIGNATURES:
                if (directory / signature).exists():
                    return stack
    return None


def _read_knowledge(stack: str) -> dict[str, str]:
    """Read ``rules.md`` and ``skills.md`` for *stack*."""
    stack_dir: Path = _TECH_STACKS_DIR / stack
    result: dict[str, str] = {}

    for filename in ("rules.md", "skills.md"):
        filepath: Path = stack_dir / filename
        try:
            result[filename] = filepath.read_text(encoding="utf-8")
        except FileNotFoundError:
            result[filename] = f"⚠ {filepath} not found."

    return result


# ---------------------------------------------------------------------------
# Tool 1 — analyze_workspace (Core)
# ---------------------------------------------------------------------------


@mcp.tool()
async def analyze_workspace(project_path: str) -> str:
    """Scan a project directory, detect the tech stack, and return rules & skills.

    Args:
        project_path: Absolute or relative path to the project root.

    Returns:
        JSON string with detected stack, rules, and skills content.
    """
    target = Path(project_path).expanduser().resolve()

    if not target.exists():
        return json.dumps(
            {"status": "error", "message": f"Path does not exist: {target}"},
            indent=2, ensure_ascii=False,
        )

    if not target.is_dir():
        return json.dumps(
            {"status": "error", "message": f"Not a directory: {target}"},
            indent=2, ensure_ascii=False,
        )

    stack = _detect_stack(target)
    if stack is None:
        return json.dumps(
            {
                "status": "unknown",
                "message": "No recognised tech stack found.",
                "scanned_path": str(target),
                "hint": "Supported: build.gradle(.kts), pubspec.yaml, package.json",
            },
            indent=2, ensure_ascii=False,
        )

    knowledge = _read_knowledge(stack)

    return json.dumps(
        {
            "status": "success",
            "detected_stack": stack,
            "project_path": str(target),
            "rules": knowledge.get("rules.md", ""),
            "skills": knowledge.get("skills.md", ""),
        },
        indent=2, ensure_ascii=False,
    )

# ---------------------------------------------------------------------------
# Helper: Workspace ID
# ---------------------------------------------------------------------------

def _auto_workspace_id(workspace_path: str = "") -> str:
    """Generate deterministic workspace ID from CWD or explicit path."""
    path = workspace_path or os.getcwd()
    return hashlib.md5(path.encode()).hexdigest()[:8]  # noqa: S324


# ---------------------------------------------------------------------------
# Tool 2 — store_working_context (L1)
# ---------------------------------------------------------------------------


@mcp.tool()
async def store_working_context(
    text_data: str,
    metadata_source: str,
    tech_stack: str = "general",
    workspace_id: str = "",
) -> str:
    """Store working context into L1 (per-workspace short-term memory).

    Use for: code files, logs, error traces, draft designs.
    Auto-cleaned after 3 days.

    Args:
        text_data: The text content to store.
        metadata_source: Label describing the origin (file path, URL, etc.).
        tech_stack: Tech stack tag (e.g. android_kotlin, flutter_dart).
        workspace_id: Workspace identifier (auto-detected from CWD if empty).

    Returns:
        JSON string reporting storage status.
    """
    ws_id = workspace_id or _auto_workspace_id()
    return await compress_and_store(text_data, metadata_source, "L1", ws_id, tech_stack)


# ---------------------------------------------------------------------------
# Tool 3 — store_knowledge (L2)
# ---------------------------------------------------------------------------


@mcp.tool()
async def store_knowledge(
    text_data: str,
    metadata_source: str,
    tech_stack: str = "general",
) -> str:
    """Store knowledge into L2 (global long-term brain).

    Use for: rules, best practices, solved bugs, boilerplate configs.
    Permanent storage, shared across all workspaces.

    Args:
        text_data: The knowledge content to store.
        metadata_source: Label describing the origin.
        tech_stack: Tech stack tag for filtering.

    Returns:
        JSON string reporting storage status.
    """
    return await compress_and_store(text_data, metadata_source, "L2", "global", tech_stack)


# ---------------------------------------------------------------------------
# Tool 4 — search_memory (Federated L1+L2)
# ---------------------------------------------------------------------------


@mcp.tool()
async def search_memory(
    query: str,
    n_results: int = 5,
    tech_stack: str = "",
    workspace_id: str = "",
) -> str:
    """Federated search across L1 (local) and L2 (global) memory.

    Queries both tiers, merges results, re-ranks by similarity distance.
    Results are tagged [L1_LOCAL] or [L2_GLOBAL] for context awareness.

    Args:
        query: Natural-language query to search for.
        n_results: Total results to return after merge (default 5).
        tech_stack: If provided, only search within this tech stack.
        workspace_id: Workspace for L1 lookup (auto-detected if empty).

    Returns:
        JSON with merged, re-ranked results from both memory tiers.
    """
    ws_id = workspace_id or _auto_workspace_id()
    stack_filter = tech_stack if tech_stack else None
    return await query_memory(query, ws_id, stack_filter, n_results)


# ---------------------------------------------------------------------------
# Tool 5 — cleanup_workspace (L1 garbage collection)
# ---------------------------------------------------------------------------


@mcp.tool()
async def cleanup_workspace(
    days: int = 3,
    workspace_id: str = "",
) -> str:
    """Delete old L1 records to free resources.

    Args:
        days: Records older than this will be deleted (default 3).
        workspace_id: Workspace to clean (auto-detected if empty).

    Returns:
        JSON with deletion count and remaining records.
    """
    ws_id = workspace_id or _auto_workspace_id()
    return await cleanup_l1(ws_id, days)


# ---------------------------------------------------------------------------
# Tool 6 — memory_stats
# ---------------------------------------------------------------------------


@mcp.tool()
async def memory_stats() -> str:
    """Get L1/L2 memory statistics: collection counts and chunk totals.

    Returns:
        JSON with L1 workspace stats and L2 global chunk count.
    """
    return await get_memory_stats()


# ---------------------------------------------------------------------------
# Tool 7 — run_terminal_command
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_terminal_command(command: str, timeout: int = 60) -> str:
    """Execute a terminal command with safety checks and timeout.

    Args:
        command: The shell command to execute.
        timeout: Max seconds before killing the process (default 60).

    Returns:
        JSON with status, exit_code, stdout, stderr, and the command.
    """
    return await execute_terminal_command(command, timeout)


# ---------------------------------------------------------------------------
# Tool 5 — sync_knowledge
# ---------------------------------------------------------------------------


@mcp.tool()
async def sync_knowledge(repo_url: str) -> str:
    """Sync the local tech_stacks/ knowledge base from a remote Git repository.

    Args:
        repo_url: HTTPS or SSH URL of the Git repository containing
            the tech_stacks content (rules.md, skills.md).

    Returns:
        JSON report with sync status (clone / pull / force_reset / error).
    """
    return await sync_knowledge_from_git(repo_url)


# ---------------------------------------------------------------------------
# Tool 6 — server_health
# ---------------------------------------------------------------------------

_SERVER_START: float = time.time()


def _format_uptime(seconds: float) -> str:
    """Convert seconds to human-readable uptime string."""
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


def _get_memory_mb() -> float:
    """Get current process RSS memory in MB (macOS/Linux)."""
    try:
        import resource
        # ru_maxrss is in bytes on macOS
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 * 1024)  # bytes → MB on macOS
    except Exception:  # noqa: BLE001
        return 0.0


@mcp.tool()
async def server_health() -> str:
    """Report MCP server health: uptime, memory, ChromaDB status, knowledge base stats.

    Returns:
        JSON with server status, resource usage, and available tech stacks.
    """
    uptime_sec = time.time() - _SERVER_START

    # ChromaDB status (lazy — don't init just for health check)
    from context_engine import _collection, _DB_PATH
    chroma_status = "initialized" if _collection is not None else "not_loaded (lazy)"
    chroma_dir = Path(_DB_PATH)
    chroma_size_mb = 0.0
    if chroma_dir.exists():
        chroma_size_mb = sum(
            f.stat().st_size for f in chroma_dir.rglob("*") if f.is_file()
        ) / (1024 * 1024)

    # Knowledge base stats
    stacks: dict[str, dict[str, int]] = {}
    if _TECH_STACKS_DIR.exists():
        for stack_dir in sorted(_TECH_STACKS_DIR.iterdir()):
            if stack_dir.is_dir() and not stack_dir.name.startswith("."):
                info: dict[str, int] = {}
                for fname in ("rules.md", "skills.md"):
                    fpath = stack_dir / fname
                    info[fname] = fpath.stat().st_size if fpath.exists() else 0
                stacks[stack_dir.name] = info

    return json.dumps(
        {
            "status": "healthy",
            "pid": os.getpid(),
            "uptime": _format_uptime(uptime_sec),
            "uptime_seconds": round(uptime_sec, 1),
            "memory_mb": round(_get_memory_mb(), 1),
            "chromadb": {
                "status": chroma_status,
                "size_mb": round(chroma_size_mb, 2),
            },
            "knowledge_base": {
                "stacks_available": len(stacks),
                "details": stacks,
            },
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

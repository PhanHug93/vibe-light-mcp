"""
TechStackLocalMCP — Entry Point.

Boots a FastMCP server that exposes five tools:

  1. ``analyze_workspace``          — detect tech stack → return rules & skills
  2. ``compress_and_store_context`` — chunk + embed text into ChromaDB
  3. ``query_local_memory``         — semantic search over stored context
  4. ``run_terminal_command``       — sandboxed shell execution
  5. ``sync_knowledge``             — git-backed knowledge sync
  6. ``server_health``               — report server status & resource usage
  7. ``usage_stats``                 — daily usage analytics & satisfaction score
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from context_engine import compress_and_store, query_memory
from execution_engine import execute_terminal_command
from knowledge_updater import sync_knowledge_from_git
from usage_tracker import record_tool_call, get_daily_stats

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

    # Track usage
    record_tool_call("analyze_workspace", stack=stack)

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
# Tool 2 — compress_and_store_context
# ---------------------------------------------------------------------------


@mcp.tool()
async def compress_and_store_context(
    text_data: str,
    metadata_source: str,
) -> str:
    """Chunk and store text into ChromaDB for later semantic retrieval.

    Args:
        text_data: The text content to compress and store.
        metadata_source: Label describing the origin (file path, URL, etc.).

    Returns:
        JSON string reporting chunk count and storage status.
    """
    result = await asyncio.to_thread(compress_and_store, text_data, metadata_source)
    record_tool_call("compress_and_store_context", query=metadata_source)
    return result


# ---------------------------------------------------------------------------
# Tool 3 — query_local_memory
# ---------------------------------------------------------------------------


@mcp.tool()
async def query_local_memory(query: str, n_results: int = 3) -> str:
    """Semantic search over stored context in ChromaDB.

    Args:
        query: Natural-language query to search for.
        n_results: Maximum number of results to return (default 3).

    Returns:
        Formatted string of the most relevant stored chunks.
    """
    result = await asyncio.to_thread(query_memory, query, n_results)
    record_tool_call("query_local_memory", query=query)
    return result


# ---------------------------------------------------------------------------
# Tool 4 — run_terminal_command
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
    result = await execute_terminal_command(command, timeout)
    record_tool_call("run_terminal_command", query=command)
    return result


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
    result = await sync_knowledge_from_git(repo_url)
    record_tool_call("sync_knowledge", query=repo_url)
    return result


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
# Tool 7 — usage_stats
# ---------------------------------------------------------------------------


@mcp.tool()
async def usage_stats(date: str = "") -> str:
    """Get daily usage analytics: tech stack usage frequency and satisfaction score.

    Satisfaction score (0–100): higher = diverse queries (good),
    lower = repeated/similar queries (knowledge base may need improvement).

    Args:
        date: Date string YYYY-MM-DD (default: today).

    Returns:
        JSON with tool usage, stack usage, and satisfaction metrics.
    """
    return get_daily_stats(date if date else None)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

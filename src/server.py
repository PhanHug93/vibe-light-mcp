"""
TechStackLocalMCP — Entry Point.

Boots a FastMCP server exposing tools for Hybrid RAG (L1/L2 Memory):

  1. ``analyze_workspace``          — detect tech stack → return rules & skills
  2. ``compress_and_store_context`` — chunk + embed text into ChromaDB
  3. ``query_local_memory``         — semantic search over stored context
  4. ``run_terminal_command``       — sandboxed shell execution
  5. ``sync_knowledge``             — git-backed knowledge sync
  6. ``server_health``               — report server status & resource usage
  7. ``usage_stats``                 — daily usage analytics & satisfaction score
"""

from __future__ import annotations

__version__: str = "1.0.6"

import asyncio
import hashlib
import json
import logging
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.config import PROJECT_ROOT, TECH_STACKS_DIR, CHROMA_DB_PATH
from src.engine.context import (
    compress_and_store,
    query_memory,
    quick_recall,
    cleanup_l1,
    get_memory_stats,
)
from src.engine.execution import execute_terminal_command
from src.engine.knowledge import sync_knowledge_from_git
from src.engine.stack_detector import detect_stack_enhanced, read_knowledge
from src.utils.markdown_utils import parse_md_sections, merge_md_sections, replace_md_section
from src.utils.usage_tracker import record_tool_call, get_daily_stats

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    stream=sys.stderr,  # CRITICAL: never write to stdout (stdio transport)
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TechStackLocalMCP")

# ---------------------------------------------------------------------------
# Constants (from centralized config)
# ---------------------------------------------------------------------------

_TECH_STACKS_DIR: Path = TECH_STACKS_DIR


# ---------------------------------------------------------------------------
# Tool 1 — analyze_workspace (Core)
# ---------------------------------------------------------------------------


@mcp.tool()
async def analyze_workspace(project_path: str) -> str:
    """Scan a project directory, detect the tech stack, and return rules & skills.

    Call this tool when user asks to:
    - Analyze, scan, or detect a project's tech stack
    - Get coding rules or skills for a project
    - Understand what technology a project uses

    Uses two-pass detection:
    1. File signature matching (fast: build.gradle.kts, pubspec.yaml, etc.)
    2. Keyword scanning (deep: scans source files for framework patterns)

    Args:
        project_path: Absolute or relative path to the project root.

    Returns:
        JSON string with detected stack, rules, skills, keyword hits,
        confidence score, and available references.
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

    detection = detect_stack_enhanced(target, _TECH_STACKS_DIR)
    stack = detection["stack"]

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

    knowledge = read_knowledge(stack, _TECH_STACKS_DIR)

    # Track usage
    record_tool_call("analyze_workspace", stack=stack)

    return json.dumps(
        {
            "status": "success",
            "detected_stack": stack,
            "detection_method": detection["method"],
            "confidence": detection["confidence"],
            "keyword_hits": detection["keyword_hits"],
            "project_path": str(target),
            "rules": knowledge.get("rules.md", ""),
            "skills": knowledge.get("skills.md", ""),
            "available_references": knowledge.get("available_references", []),
        },
        indent=2, ensure_ascii=False,
    )

# ---------------------------------------------------------------------------
# Tool 1b — read_reference (Progressive Disclosure)
# ---------------------------------------------------------------------------


@mcp.tool()
async def read_reference(stack: str, reference_name: str) -> str:
    """Read a detailed reference document from a tech stack's references/ directory.

    Call this tool when user asks to:
    - See detailed examples for a specific topic (e.g. architecture, compose)
    - Deep dive into a reference document
    - Get heavy implementation examples beyond core rules

    Only loads content on demand to save context window.
    Use analyze_workspace first to see available_references.

    Args:
        stack: Tech stack key (e.g. android_kotlin, flutter_dart).
        reference_name: Filename of the reference (e.g. architecture.md).

    Returns:
        JSON with reference content or error message.
    """
    refs_dir = _TECH_STACKS_DIR / stack / "references"

    if not refs_dir.is_dir():
        return json.dumps(
            {"status": "error", "message": f"No references/ directory for stack '{stack}'."},
            indent=2, ensure_ascii=False,
        )

    # Ensure .md extension
    if not reference_name.endswith(".md"):
        reference_name += ".md"

    ref_path = refs_dir / reference_name
    if not ref_path.is_file():
        available = [f.name for f in refs_dir.iterdir() if f.is_file() and f.suffix == ".md"]
        return json.dumps(
            {
                "status": "error",
                "message": f"Reference '{reference_name}' not found.",
                "available_references": available,
            },
            indent=2, ensure_ascii=False,
        )

    content = ref_path.read_text(encoding="utf-8")
    record_tool_call("read_reference", stack=stack)

    return json.dumps(
        {
            "status": "success",
            "stack": stack,
            "reference": reference_name,
            "content": content,
        },
        indent=2, ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Helper: Workspace ID
# ---------------------------------------------------------------------------

_WORKSPACE_ERROR_MSG: str = (
    "ERROR: workspace_path is REQUIRED. You MUST provide the absolute path "
    "of the project root directory (e.g. /Users/admin/projects/my-app). "
    "Infer this from the file paths the user is currently editing. "
    "DO NOT leave this empty — call this tool again with workspace_path filled in."
)


def _make_workspace_id(workspace_path: str) -> str:
    """Generate deterministic workspace ID from an explicit project path.

    Raises *ValueError* if *workspace_path* is empty — callers must handle
    this and return a JSON error to the agent.
    """
    if not workspace_path or not workspace_path.strip():
        raise ValueError(_WORKSPACE_ERROR_MSG)
    return hashlib.md5(workspace_path.strip().encode()).hexdigest()[:8]  # noqa: S324


# ---------------------------------------------------------------------------
# Tool 2 — store_working_context (L1)
# ---------------------------------------------------------------------------


@mcp.tool()
async def store_working_context(
    text_data: str,
    metadata_source: str,
    workspace_path: str,
    tech_stack: str = "general",
) -> str:
    """Store working context into L1 (per-workspace short-term memory).

    Call this tool when user asks to:
    - Save, store, or remember code, logs, or error traces
    - Keep context about current work for later retrieval
    - Cache file contents or debugging output

    Use for: code files, logs, error traces, draft designs.
    Auto-cleaned after 3 days.

    Args:
        text_data: The text content to store.
        metadata_source: Label describing the origin (file path, URL, etc.).
        workspace_path: ⚠️ REQUIRED. The absolute path of the project root
            directory (e.g. /Users/admin/projects/my-android-app). Infer this
            from the file paths the user is currently editing. DO NOT omit.
        tech_stack: Tech stack tag (e.g. android_kotlin, flutter_dart).

    Returns:
        JSON string reporting storage status.
    """
    try:
        ws_id = _make_workspace_id(workspace_path)
    except ValueError:
        return json.dumps(
            {"status": "error", "message": _WORKSPACE_ERROR_MSG},
            ensure_ascii=False,
        )
    result = await compress_and_store(text_data, metadata_source, "L1", ws_id, tech_stack)
    record_tool_call("compress_and_store_context", query=metadata_source)
    return result


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

    Call this tool when user asks to:
    - Save a rule, best practice, or lesson learned permanently
    - Store a solved bug fix or boilerplate config for reuse
    - Add knowledge that should be available across all projects

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
    workspace_path: str,
    n_results: int = 5,
    tech_stack: str = "",
) -> str:
    """Federated search across L1 (local) and L2 (global) memory.

    Call this tool when user asks to:
    - Search, find, or recall stored context or knowledge
    - Look up previous code, logs, errors, or best practices
    - Query the memory / knowledge base for relevant information

    Queries both tiers, merges results, re-ranks by similarity distance.
    Results are tagged [L1_LOCAL] or [L2_GLOBAL] for context awareness.

    Args:
        query: Natural-language query to search for.
        workspace_path: ⚠️ REQUIRED. The absolute path of the project root
            directory (e.g. /Users/admin/projects/my-android-app). Infer this
            from the file paths the user is currently editing. DO NOT omit.
        n_results: Total results to return after merge (default 5).
        tech_stack: If provided, only search within this tech stack.

    Returns:
        JSON with merged, re-ranked results from both memory tiers.
    """
    try:
        ws_id = _make_workspace_id(workspace_path)
    except ValueError:
        return json.dumps(
            {"status": "error", "message": _WORKSPACE_ERROR_MSG},
            ensure_ascii=False,
        )
    result = await query_memory(query, ws_id, tech_stack or None, n_results)
    record_tool_call("query_local_memory", query=query)
    return result


# ---------------------------------------------------------------------------
# Tool 4b — auto_recall (Context Recall for AI Agents)
# ---------------------------------------------------------------------------

# Rate limiter state
_recall_cache: dict[str, tuple[float, str]] = {}  # hash → (timestamp, result)
_RECALL_COOLDOWN: float = 3.0   # seconds between actual queries (was 10.0)
_RECALL_CACHE_SIZE: int = 20    # max cached results


@mcp.tool()
async def auto_recall(
    user_message: str,
    workspace_path: str,
    tech_stack: str = "",
    n_results: int = 3,
) -> str:
    """⚡ Auto-retrieve relevant context from memory for the current conversation.

    IMPORTANT: Call this at the START of every conversation to recall
    previous context and avoid losing information from past sessions.
    Also call when the conversation is getting long (>10 turns) to
    refresh your memory.

    This tool is:
    - Rate-limited (max 1 query per 3s, duplicates return cached results)
    - Fail-safe (always returns valid JSON, never blocks)
    - Fast (5s timeout, compact output ≤3000 chars)

    Args:
        user_message: The user's current message to find relevant context for.
        workspace_path: ⚠️ REQUIRED. The absolute path of the project root
            directory (e.g. /Users/admin/projects/my-android-app). Infer this
            from the file paths the user is currently editing. DO NOT omit.
        tech_stack: Filter results by tech stack (optional).
        n_results: Max context chunks to return (default 3, max 5).

    Returns:
        JSON with status and recalled context (if any).
    """
    import time as _time

    try:
        ws_id = _make_workspace_id(workspace_path)
    except ValueError:
        return json.dumps(
            {"status": "error", "message": _WORKSPACE_ERROR_MSG},
            ensure_ascii=False,
        )
    n_results = min(n_results, 5)

    # --- Rate limiter + Dedup ---
    # Include tech_stack in hash to avoid cross-context cache hits
    # when user sends similar short queries ("fix this") in different stacks
    query_hash = hashlib.md5(  # noqa: S324
        f"{user_message}:{ws_id}:{tech_stack}".encode(),
    ).hexdigest()[:12]
    now = _time.time()

    if query_hash in _recall_cache:
        cached_time, cached_result = _recall_cache[query_hash]
        if now - cached_time < _RECALL_COOLDOWN:
            return json.dumps({
                "status": "cached",
                "message": "Using cached recall (rate-limited).",
                "context": cached_result,
            }, ensure_ascii=False)

    # Prune old cache entries
    if len(_recall_cache) > _RECALL_CACHE_SIZE:
        oldest_keys = sorted(_recall_cache, key=lambda k: _recall_cache[k][0])
        for k in oldest_keys[:len(oldest_keys) // 2]:
            del _recall_cache[k]

    # --- Recall ---
    try:
        context = await quick_recall(
            query=user_message,
            workspace_id=ws_id,
            tech_stack=tech_stack or None,
            n_results=n_results,
        )
    except Exception:  # noqa: BLE001
        context = ""

    # Cache result
    _recall_cache[query_hash] = (now, context)
    record_tool_call("auto_recall", query=user_message[:100])

    if not context:
        return json.dumps({
            "status": "no_context",
            "message": "No relevant context found in memory. This is normal for new topics.",
        }, ensure_ascii=False)

    return json.dumps({
        "status": "success",
        "message": "Relevant context recalled from memory. Use this to inform your response.",
        "context": context,
    }, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Tool 5 — cleanup_workspace (L1 garbage collection)
# ---------------------------------------------------------------------------


@mcp.tool()
async def cleanup_workspace(
    workspace_path: str,
    days: int = 3,
) -> str:
    """Delete old L1 records to free resources.

    Call this tool when user asks to:
    - Clean up, clear, or free memory / context storage
    - Delete old or expired workspace data
    - Reset the local working memory

    Args:
        workspace_path: ⚠️ REQUIRED. The absolute path of the project root
            directory (e.g. /Users/admin/projects/my-android-app). Infer this
            from the file paths the user is currently editing. DO NOT omit.
        days: Records older than this will be deleted (default 3).

    Returns:
        JSON with deletion count and remaining records.
    """
    try:
        ws_id = _make_workspace_id(workspace_path)
    except ValueError:
        return json.dumps(
            {"status": "error", "message": _WORKSPACE_ERROR_MSG},
            ensure_ascii=False,
        )
    return await cleanup_l1(ws_id, days)


# ---------------------------------------------------------------------------
# Tool 6 — memory_stats
# ---------------------------------------------------------------------------


@mcp.tool()
async def memory_stats() -> str:
    """Get L1/L2 memory statistics: collection counts and chunk totals.

    Call this tool when user asks to:
    - Check memory usage, storage stats, or how much context is stored
    - View workspace or knowledge base statistics
    - See how many chunks or collections exist

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

    Call this tool when user asks to:
    - Run a shell / terminal / bash command
    - Execute a script, build, or deployment command
    - Check system info, file listings, or process status

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

    Call this tool when user asks to:
    - Update, sync, or refresh the knowledge base / rules / skills
    - Pull latest tech stack rules from a Git repo
    - Import or download coding standards

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

    Call this tool when user asks to:
    - Check server health, status, or uptime
    - See RAM usage or resource consumption
    - Verify the MCP server is running properly

    Returns:
        JSON with server status, resource usage, and available tech stacks.
    """
    uptime_sec = time.time() - _SERVER_START

    # ChromaDB status — check via HTTP heartbeat (don't import internal state)
    try:
        import httpx
        resp = httpx.get("http://localhost:8888/api/v2/heartbeat", timeout=2)
        chroma_status = "running" if resp.status_code == 200 else "error"
    except Exception:
        chroma_status = "not_running"
    chroma_dir = Path.home() / ".mcp_global_db"
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
            "version": __version__,
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

    Call this tool when user asks to:
    - View usage statistics or analytics
    - Check which tech stacks are most used
    - See satisfaction score or query patterns

    Satisfaction score (0–100): higher = diverse queries (good),
    lower = repeated/similar queries (knowledge base may need improvement).

    Args:
        date: Date string YYYY-MM-DD (default: today).

    Returns:
        JSON with tool usage, stack usage, and satisfaction metrics.
    """
    return get_daily_stats(date if date else None)


# ---------------------------------------------------------------------------
# Tool 10 — manage_chroma (P6: ISP — separated from self_update)
# ---------------------------------------------------------------------------

_MCP_ROOT: Path = PROJECT_ROOT


@mcp.tool()
async def manage_chroma(action: str) -> str:
    """Start, stop, or check ChromaDB database server status.

    Call this tool when user asks to:
    - Start or initialize the database / ChromaDB
    - Stop or shutdown the database / ChromaDB
    - Check if database / ChromaDB is running

    Args:
        action: One of:
            - ``start``  — Start ChromaDB HTTP server (port 8888)
            - ``stop``   — Stop ChromaDB HTTP server
            - ``status`` — Check if ChromaDB is running

    Returns:
        JSON with action result.
    """
    import subprocess

    action = action.strip().lower()

    if action == "status":
        try:
            import httpx  # noqa: F811
            resp = httpx.get("http://localhost:8888/api/v2/heartbeat", timeout=3)
            heartbeat = resp.json()
            return json.dumps({
                "status": "running",
                "port": 8888,
                "heartbeat": heartbeat,
            }, indent=2)
        except Exception:
            pass

        # Fallback: check via lsof
        result = subprocess.run(
            ["lsof", "-i", ":8888"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.dumps({
                "status": "running",
                "port": 8888,
                "details": result.stdout.strip().split("\n")[:3],
            }, indent=2)

        return json.dumps({
            "status": "stopped",
            "message": "ChromaDB not running on port 8888.",
            "hint": "Use action 'start' to launch it.",
        }, indent=2)

    elif action == "start":
        # Check if already running
        check = subprocess.run(
            ["lsof", "-i", ":8888"],
            capture_output=True, text=True, timeout=5,
        )
        if check.returncode == 0 and check.stdout.strip():
            return json.dumps({
                "status": "already_running",
                "message": "ChromaDB is already running on port 8888.",
            }, indent=2)

        # Find chroma binary
        chroma_bin = str(_MCP_ROOT / ".venv" / "bin" / "chroma")
        if not Path(chroma_bin).exists():
            chroma_check = subprocess.run(
                ["which", "chroma"], capture_output=True, text=True,
            )
            chroma_bin = chroma_check.stdout.strip() if chroma_check.returncode == 0 else ""

        if not chroma_bin:
            return json.dumps({
                "status": "error",
                "message": "chroma CLI not found. Install: pip install chromadb",
            }, indent=2)

        db_path = str(CHROMA_DB_PATH)
        CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

        # Start as background process (fd leak fixed)
        stdout_f = open("/tmp/chromadb.stdout.log", "a")  # noqa: SIM115
        stderr_f = open("/tmp/chromadb.stderr.log", "a")  # noqa: SIM115
        subprocess.Popen(
            [chroma_bin, "run", "--path", db_path, "--port", "8888"],
            stdout=stdout_f,
            stderr=stderr_f,
            start_new_session=True,
        )
        stdout_f.close()
        stderr_f.close()

        # Wait a moment and verify
        await asyncio.sleep(3)

        verify = subprocess.run(
            ["lsof", "-i", ":8888"],
            capture_output=True, text=True, timeout=5,
        )
        started = verify.returncode == 0 and verify.stdout.strip()

        return json.dumps({
            "status": "started" if started else "failed",
            "port": 8888,
            "db_path": db_path,
            "logs": "/tmp/chromadb.stdout.log",
            "message": "ChromaDB server launched" if started else "Check /tmp/chromadb.stderr.log",
        }, indent=2)

    elif action == "stop":
        result = subprocess.run(
            ["lsof", "-ti", ":8888"],
            capture_output=True, text=True, timeout=5,
        )
        pids = result.stdout.strip().split("\n") if result.stdout.strip() else []

        if not pids:
            return json.dumps({
                "status": "not_running",
                "message": "ChromaDB is not running.",
            }, indent=2)

        for pid in pids:
            if pid.isdigit():
                subprocess.run(["kill", pid], timeout=5)

        await asyncio.sleep(1)

        return json.dumps({
            "status": "stopped",
            "killed_pids": pids,
            "message": "ChromaDB server stopped.",
        }, indent=2)

    else:
        return json.dumps({
            "status": "error",
            "message": f"Unknown action: '{action}'",
            "available_actions": ["start", "stop", "status"],
        }, indent=2)


# ---------------------------------------------------------------------------
# Tool 10b — self_update (P6: ISP — separated from manage_chroma)
# ---------------------------------------------------------------------------


@mcp.tool()
async def self_update() -> str:
    """Pull latest MCP server code from Git remote.

    Call this tool when user asks to:
    - Update or upgrade the MCP server code
    - Pull latest changes for the MCP server

    Returns:
        JSON with git pull result and restart hint.
    """
    import subprocess

    result = subprocess.run(
        ["git", "pull", "--rebase"],
        capture_output=True, text=True,
        cwd=str(_MCP_ROOT), timeout=30,
    )

    return json.dumps({
        "status": "success" if result.returncode == 0 else "error",
        "action": "git pull --rebase",
        "stdout": result.stdout.strip()[-500:],
        "stderr": result.stderr.strip()[-300:] if result.returncode != 0 else "",
        "hint": "Restart MCP server to apply updates." if result.returncode == 0 else "",
    }, indent=2)


# Markdown helpers imported from src.utils.markdown_utils


# ---------------------------------------------------------------------------
# Tool 11 — update_tech_stack (Merge-aware Knowledge Update)
# ---------------------------------------------------------------------------


@mcp.tool()
async def update_tech_stack(
    stack: str,
    target_file: str,
    new_content: str,
    mode: str = "append",
    section_header: str = "",
) -> str:
    """Update a tech stack knowledge file with merge support (no data loss).

    Call this tool when user asks to:
    - Add new rules, skills, or references to an existing tech stack
    - Update a specific section of rules or skills
    - Extend the knowledge base with additional content

    Three modes:
    - ``append``          — Add new sections to end of file, skip duplicates
    - ``replace_section`` — Replace a specific ## section (requires section_header)
    - ``overwrite``       — Replace entire file content (use with caution)

    Args:
        stack: Tech stack key (e.g. python, android_kotlin, flutter_dart).
        target_file: One of "rules", "skills", or a reference filename
            (e.g. "testing" → references/testing.md).
        new_content: The markdown content to add or replace.
        mode: Update mode — "append" (default), "replace_section", "overwrite".
        section_header: Required for replace_section mode.
            The H2 header text to replace (without "## " prefix).

    Returns:
        JSON with update status, sections added/skipped (append mode),
        or replacement result (replace_section mode).
    """
    stack_dir = TECH_STACKS_DIR / stack

    # Resolve target file path
    if target_file in ("rules", "rules.md"):
        target_path = stack_dir / "rules.md"
    elif target_file in ("skills", "skills.md"):
        target_path = stack_dir / "skills.md"
    else:
        # Treat as a reference file
        ref_name = target_file if target_file.endswith(".md") else f"{target_file}.md"
        target_path = stack_dir / "references" / ref_name

    # Validate mode
    valid_modes = ("append", "replace_section", "overwrite")
    if mode not in valid_modes:
        return json.dumps({
            "status": "error",
            "message": f"Invalid mode: '{mode}'. Use one of: {valid_modes}",
        }, indent=2, ensure_ascii=False)

    if mode == "replace_section" and not section_header:
        return json.dumps({
            "status": "error",
            "message": "section_header is required for replace_section mode.",
        }, indent=2, ensure_ascii=False)

    # Ensure parent directories exist
    target_path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content (empty string if file doesn't exist yet)
    existing_content = ""
    if target_path.is_file():
        existing_content = target_path.read_text(encoding="utf-8")

    # --- Mode: overwrite ---
    if mode == "overwrite":
        target_path.write_text(new_content, encoding="utf-8")
        record_tool_call("update_tech_stack", stack=stack)
        return json.dumps({
            "status": "success",
            "mode": "overwrite",
            "stack": stack,
            "file": str(target_path.relative_to(PROJECT_ROOT)),
            "size": len(new_content),
            "message": "File overwritten completely.",
        }, indent=2, ensure_ascii=False)

    # --- Mode: append (with dedup) ---
    if mode == "append":
        if not existing_content:
            # No existing file → just write new content
            target_path.write_text(new_content, encoding="utf-8")
            record_tool_call("update_tech_stack", stack=stack)
            return json.dumps({
                "status": "success",
                "mode": "append",
                "stack": stack,
                "file": str(target_path.relative_to(PROJECT_ROOT)),
                "message": "New file created (no existing content).",
                "size": len(new_content),
            }, indent=2, ensure_ascii=False)

        merged, added, skipped = merge_md_sections(existing_content, new_content)
        target_path.write_text(merged, encoding="utf-8")
        record_tool_call("update_tech_stack", stack=stack)
        return json.dumps({
            "status": "success",
            "mode": "append",
            "stack": stack,
            "file": str(target_path.relative_to(PROJECT_ROOT)),
            "sections_added": added,
            "sections_skipped_duplicate": skipped,
            "message": (
                f"Added {len(added)} new section(s), "
                f"skipped {len(skipped)} duplicate(s)."
            ),
        }, indent=2, ensure_ascii=False)

    # --- Mode: replace_section ---
    if mode == "replace_section":
        if not existing_content:
            return json.dumps({
                "status": "error",
                "message": f"File does not exist yet. Use 'append' mode to create it first.",
            }, indent=2, ensure_ascii=False)

        updated, found = replace_md_section(
            existing_content, section_header, new_content,
        )
        if not found:
            # List available sections for hint
            sections = parse_md_sections(existing_content)
            available = [h for h in sections if h != "__preamble__"]
            return json.dumps({
                "status": "error",
                "message": f"Section '## {section_header}' not found.",
                "available_sections": available,
            }, indent=2, ensure_ascii=False)

        target_path.write_text(updated, encoding="utf-8")
        record_tool_call("update_tech_stack", stack=stack)
        return json.dumps({
            "status": "success",
            "mode": "replace_section",
            "stack": stack,
            "file": str(target_path.relative_to(PROJECT_ROOT)),
            "replaced_section": section_header,
            "message": f"Section '## {section_header}' updated successfully.",
        }, indent=2, ensure_ascii=False)

    # Should not reach here
    return json.dumps({"status": "error", "message": "Unexpected state."}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

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

__version__: str = "1.0.2"

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
    ("Podfile",             "ios_swift"),
    ("Package.swift",       "ios_swift"),
    ("package.json",        "react_native"),  # checked via keyword scan
    ("package.json",        "vue_js"),
]

_SEARCH_DEPTH: int = 1  # root + one level deep

# Keyword triggers: scan source file content for framework-specific patterns.
_STACK_TRIGGERS: dict[str, dict[str, list[str]]] = {
    "android_kotlin": {
        "extensions": [".kt", ".kts"],
        "keywords": [
            "@Composable", "ViewModel", "Hilt", "@Inject", "@Provides",
            "suspend fun", "StateFlow", "viewModelScope", "NavHost",
            "Room", "@Entity", "@Dao", "Retrofit", "OkHttpClient",
        ],
    },
    "flutter_dart": {
        "extensions": [".dart"],
        "keywords": [
            "StatelessWidget", "StatefulWidget", "BuildContext",
            "Bloc", "Cubit", "Provider", "GetX", "Riverpod",
            "GoRouter", "AutoRoute", "pubspec",
        ],
    },
    "kmp": {
        "extensions": [".kt", ".kts"],
        "keywords": [
            "expect ", "actual ", "commonMain", "Multiplatform",
            "iosMain", "androidMain", "KMM",
        ],
    },
    "vue_js": {
        "extensions": [".vue", ".ts", ".js"],
        "keywords": [
            "defineComponent", "ref(", "reactive(", "computed(",
            "Pinia", "createApp", "createRouter", "<template>",
            "v-model", "v-if", "v-for",
        ],
    },
    "react_native": {
        "extensions": [".tsx", ".ts", ".jsx"],
        "keywords": [
            "react-native", "React Native", "NavigationContainer",
            "createNativeStackNavigator", "FlatList", "StyleSheet",
            "useNavigation", "Pressable", "SafeAreaView",
        ],
    },
    "ios_swift": {
        "extensions": [".swift"],
        "keywords": [
            "@State", "@Binding", "@ObservedObject", "@StateObject",
            "NavigationStack", "@MainActor", "async throws",
            "UIViewController", "SwiftUI", "Combine",
        ],
    },
}

_KEYWORD_SCAN_MAX_FILES: int = 20
_KEYWORD_SCAN_MAX_BYTES: int = 50_000  # per file


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


def _scan_keywords(project_path: Path, stack: str) -> dict[str, int]:
    """Scan source files for keyword hits. Returns {keyword: count}."""
    triggers = _STACK_TRIGGERS.get(stack)
    if not triggers:
        return {}

    extensions = set(triggers["extensions"])
    keywords = triggers["keywords"]
    hits: dict[str, int] = {}
    files_scanned = 0

    for source_file in project_path.rglob("*"):
        if files_scanned >= _KEYWORD_SCAN_MAX_FILES:
            break
        if not source_file.is_file():
            continue
        if source_file.suffix not in extensions:
            continue
        # Skip hidden dirs, build dirs, etc.
        parts = source_file.relative_to(project_path).parts
        if any(p.startswith(".") or p in ("build", "node_modules", ".gradle") for p in parts):
            continue

        try:
            content = source_file.read_text(encoding="utf-8", errors="ignore")
            if len(content) > _KEYWORD_SCAN_MAX_BYTES:
                content = content[:_KEYWORD_SCAN_MAX_BYTES]
        except (OSError, UnicodeDecodeError):
            continue

        files_scanned += 1
        for kw in keywords:
            count = content.count(kw)
            if count > 0:
                hits[kw] = hits.get(kw, 0) + count

    return hits


def _detect_stack_enhanced(project_path: Path) -> dict:
    """Enhanced detection: file signature + keyword scan.

    Returns dict with: stack, method, keyword_hits, confidence.
    """
    stack = _detect_stack(project_path)
    method = "file_signature" if stack else "none"

    if stack is None:
        # Fallback: try keyword-only detection across all stacks
        best_stack = None
        best_score = 0
        for candidate_stack in _STACK_TRIGGERS:
            hits = _scan_keywords(project_path, candidate_stack)
            score = sum(hits.values())
            if score > best_score:
                best_score = score
                best_stack = candidate_stack
        if best_stack and best_score >= 3:
            stack = best_stack
            method = "keyword_only"

    # Keyword scan for matched stack
    keyword_hits: dict[str, int] = {}
    confidence = 0.0
    if stack:
        keyword_hits = _scan_keywords(project_path, stack)
        total_hits = sum(keyword_hits.values())
        unique_keywords = len(keyword_hits)

        if method == "file_signature":
            # File match + keywords → high confidence
            confidence = min(0.7 + (unique_keywords * 0.05), 1.0)
        else:
            # Keyword-only → lower base confidence
            confidence = min(0.3 + (unique_keywords * 0.07), 0.9)

        if method == "file_signature" and keyword_hits:
            method = "file_signature + keyword_scan"

    return {
        "stack": stack,
        "method": method,
        "keyword_hits": keyword_hits,
        "confidence": round(confidence, 2),
    }


def _read_knowledge(stack: str) -> dict:
    """Read core rules/skills + list available references for *stack*."""
    stack_dir: Path = _TECH_STACKS_DIR / stack
    result: dict[str, str | list[str]] = {}

    # Core files (always loaded)
    for filename in ("rules.md", "skills.md"):
        filepath: Path = stack_dir / filename
        try:
            result[filename] = filepath.read_text(encoding="utf-8")
        except FileNotFoundError:
            result[filename] = f"⚠ {filepath} not found."

    # Progressive disclosure: list references (loaded on demand)
    refs_dir = stack_dir / "references"
    if refs_dir.is_dir():
        result["available_references"] = sorted(
            f.name for f in refs_dir.iterdir()
            if f.is_file() and f.suffix == ".md"
        )
    else:
        result["available_references"] = []

    return result


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

    detection = _detect_stack_enhanced(target)
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

    knowledge = _read_knowledge(stack)

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

    Call this tool when user asks to:
    - Save, store, or remember code, logs, or error traces
    - Keep context about current work for later retrieval
    - Cache file contents or debugging output

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
    result = await asyncio.to_thread(compress_and_store, text_data, metadata_source)
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
    n_results: int = 5,
    tech_stack: str = "",
    workspace_id: str = "",
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
        n_results: Total results to return after merge (default 5).
        tech_stack: If provided, only search within this tech stack.
        workspace_id: Workspace for L1 lookup (auto-detected if empty).

    Returns:
        JSON with merged, re-ranked results from both memory tiers.
    """
    result = await asyncio.to_thread(query_memory, query, n_results)
    record_tool_call("query_local_memory", query=query)
    return result


# ---------------------------------------------------------------------------
# Tool 5 — cleanup_workspace (L1 garbage collection)
# ---------------------------------------------------------------------------


@mcp.tool()
async def cleanup_workspace(
    days: int = 3,
    workspace_id: str = "",
) -> str:
    """Delete old L1 records to free resources.

    Call this tool when user asks to:
    - Clean up, clear, or free memory / context storage
    - Delete old or expired workspace data
    - Reset the local working memory

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
# Tool 10 — manage_server
# ---------------------------------------------------------------------------

_MCP_ROOT: Path = Path(__file__).resolve().parent


@mcp.tool()
async def manage_server(action: str) -> str:
    """Start, stop, or check ChromaDB database server. Also update MCP code.

    Call this tool when user asks to:
    - Start or initialize the database / ChromaDB
    - Stop or shutdown the database / ChromaDB
    - Check if database / ChromaDB is running
    - Update or upgrade the MCP server code

    Args:
        action: One of:
            - ``chroma_start``  — Start ChromaDB HTTP server (port 8888)
            - ``chroma_stop``   — Stop ChromaDB HTTP server
            - ``chroma_status`` — Check if ChromaDB is running
            - ``self_update``   — Pull latest MCP code from Git remote

    Returns:
        JSON with action result.
    """
    import subprocess

    action = action.strip().lower()

    if action == "chroma_status":
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
            "hint": "Use action 'chroma_start' to launch it.",
        }, indent=2)

    elif action == "chroma_start":
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

        db_path = str(Path.home() / ".mcp_global_db")
        Path(db_path).mkdir(parents=True, exist_ok=True)

        # Start as background process
        subprocess.Popen(
            [chroma_bin, "run", "--path", db_path, "--port", "8888"],
            stdout=open("/tmp/chromadb.stdout.log", "a"),
            stderr=open("/tmp/chromadb.stderr.log", "a"),
            start_new_session=True,
        )

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

    elif action == "chroma_stop":
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

    elif action == "self_update":
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

    else:
        return json.dumps({
            "status": "error",
            "message": f"Unknown action: '{action}'",
            "available_actions": [
                "chroma_start",
                "chroma_stop",
                "chroma_status",
                "self_update",
            ],
        }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

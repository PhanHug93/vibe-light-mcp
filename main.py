#!/usr/bin/env python3
"""Entry point for TechStack Local MCP Server.

Supports 3 transport protocols:
    stdio             — default, for Antigravity/Claude (pipe-based)
    sse               — HTTP + Server-Sent Events (streaming)
    streamable-http   — Newer MCP spec, single /mcp endpoint (streaming)

Usage::

    # Default: stdio (backward compatible)
    python main.py

    # SSE server on port 8000
    python main.py --transport sse
    python main.py --transport sse --port 9000

    # Streamable HTTP
    python main.py --transport streamable-http --port 8000

    # Environment variables (alternative to CLI)
    MCP_TRANSPORT=sse MCP_PORT=9000 python main.py

The actual server implementation lives in ``src/server.py``.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import sys
import time
from pathlib import Path

# Ensure the project root is on sys.path so that ``src.*`` imports work
# regardless of how the MCP client launches this script.
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.config import MCP_TRANSPORT, MCP_HOST, MCP_PORT, MCP_LOCK_FILE  # noqa: E402


# ---------------------------------------------------------------------------
# Startup Migration — detect & fix embedding function mismatches
# ---------------------------------------------------------------------------


def _run_startup_migration() -> None:
    """Check all L1/L2 collections for embedding mismatches and migrate.

    Best-effort: if ChromaDB is unreachable (e.g. stdio transport without
    a running ChromaDB server), this is a silent no-op.  Migration will
    run on the next successful startup.
    """
    import logging as _logging

    _log = _logging.getLogger("startup.migration")

    try:
        from src.db.embedding import get_embedding_fn
        from src.config import CHROMA_HOST, CHROMA_PORT

        import chromadb

        ef = get_embedding_fn()
        if ef is None:
            _log.info("No embedding function available — skipping migration check.")
            return

        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        client.heartbeat()

        from src.db.migrate_embeddings import check_and_migrate

        report = check_and_migrate(client, ef)

        if report.get("migrated"):
            _log.info("Migration report: %s", report["summary"])
        else:
            _log.info("No embedding migration needed.")

    except Exception as exc:  # noqa: BLE001
        # Non-fatal: ChromaDB might not be running yet (stdio mode)
        _log.debug("Startup migration skipped (ChromaDB not reachable): %s", exc)


# ---------------------------------------------------------------------------
# Singleton Lock — prevents multiple SSE/HTTP servers on the same port
# ---------------------------------------------------------------------------


def _is_process_alive(pid: int) -> bool:
    """Check if a process with the given PID is still running."""
    try:
        os.kill(pid, 0)  # Signal 0 = check existence, no actual signal sent
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Process exists but we don't have permission — still alive
        return True


def _check_singleton(port: int) -> bool:
    """Check if another SSE/HTTP server is already running on *port*.

    Returns ``True`` if safe to start (no other server running).
    Returns ``False`` if another server is alive on the same port.
    """
    if not MCP_LOCK_FILE.exists():
        return True  # No lock — safe to start

    try:
        lock_data = json.loads(MCP_LOCK_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        # Corrupt or unreadable lock file — remove and proceed
        MCP_LOCK_FILE.unlink(missing_ok=True)
        return True

    lock_pid = lock_data.get("pid")
    lock_port = lock_data.get("port")
    lock_started = lock_data.get("started_at", "unknown")

    if lock_pid and _is_process_alive(lock_pid):
        print(
            f"[MCP] ⚠ SSE server already running (pid={lock_pid}, "
            f"port={lock_port}, started={lock_started}).\n"
            f"[MCP] → To connect from another IDE, use cascade_bridge.py:\n"
            f"[MCP]     MCP_BRIDGE_URL=http://127.0.0.1:{lock_port} "
            f"python cascade_bridge.py\n"
            f"[MCP] → Or use stdio transport instead (supports multi-instance):\n"
            f"[MCP]     python main.py --transport stdio\n"
            f"[MCP] Exiting.",
            file=sys.stderr,
        )
        return False

    # Stale lock (process is dead) — clean up and proceed
    print(
        f"[MCP] Removing stale lock file (pid={lock_pid} is no longer alive).",
        file=sys.stderr,
    )
    MCP_LOCK_FILE.unlink(missing_ok=True)
    return True


def _create_lock_file(pid: int, port: int) -> None:
    """Write lock file atomically (exclusive create to prevent TOCTOU race)."""
    lock_data = {
        "pid": pid,
        "port": port,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    content = json.dumps(lock_data, indent=2)
    try:
        # O_CREAT | O_EXCL → fail if file already exists (atomic check+create)
        fd = os.open(str(MCP_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
    except FileExistsError:
        # Race lost — another process created the lock between check and here.
        # Overwrite with our data (current behavior as fallback).
        MCP_LOCK_FILE.write_text(content, encoding="utf-8")


def _cleanup_lock() -> None:
    """Remove lock file on exit. Safe to call multiple times."""
    try:
        if MCP_LOCK_FILE.exists():
            # Only remove if WE own it (our PID matches)
            lock_data = json.loads(MCP_LOCK_FILE.read_text(encoding="utf-8"))
            if lock_data.get("pid") == os.getpid():
                MCP_LOCK_FILE.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        # Best-effort cleanup — never crash on exit
        pass


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments with env-var fallbacks from config."""
    parser = argparse.ArgumentParser(
        description="TechStack Local MCP Server",
    )
    parser.add_argument(
        "--transport",
        "-t",
        choices=["stdio", "sse", "streamable-http"],
        default=MCP_TRANSPORT,
        help="Transport protocol (default: %(default)s, env: MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=MCP_HOST,
        help="Bind address for HTTP transports (default: %(default)s, env: MCP_HOST)",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=MCP_PORT,
        help="Listen port for HTTP transports (default: %(default)s, env: MCP_PORT)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Boot the MCP server with the selected transport."""
    args = _parse_args()

    # ── Singleton check for SSE / HTTP transports ────────────────────
    if args.transport != "stdio":
        if not _check_singleton(args.port):
            sys.exit(0)  # Exit gracefully — another server is handling it

        # Create lock file and register cleanup
        _create_lock_file(os.getpid(), args.port)
        atexit.register(_cleanup_lock)

        # Also clean up on SIGTERM/SIGINT (graceful shutdown)
        def _signal_handler(signum, frame):
            _cleanup_lock()
            sys.exit(0)

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

    # Import server (registers all tools via decorators)
    from src.server import mcp, __version__  # noqa: E402

    # Configure host/port for HTTP transports
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    # B1: Pre-warm embedding model before event loop starts
    # Avoids 2-5s cold-start block on the first tool call.
    from src.db.embedding import pre_warm_embedding  # noqa: E402

    pre_warm_embedding()

    # B2: Auto-migrate collections with mismatched embedding functions.
    # Safe for old Docker users upgrading from versions that used the
    # implicit default embedding.  Runs once, skips if already compatible.
    _run_startup_migration()

    # Startup diagnostic (stderr only — never pollute stdout/stdio)
    transport_info = f"transport={args.transport}"
    if args.transport != "stdio":
        transport_info += f", {args.host}:{args.port}"

    print(
        f"[MCP] TechStackLocalMCP v{__version__} starting "
        f"(pid={os.getpid()}, {transport_info})",
        file=sys.stderr,
    )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

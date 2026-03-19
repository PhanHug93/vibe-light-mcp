"""System-related MCP tools — health, chroma management, self-update, terminal.

Extracted from ``server.py`` for SRP compliance.

⚠ All subprocess calls use ``asyncio.create_subprocess_exec`` to avoid
blocking the event loop (Review Fix #2).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.config import PROJECT_ROOT, TECH_STACKS_DIR, CHROMA_DB_PATH
from src.config import CHROMA_HOST, CHROMA_PORT
from src.engine.execution import execute_terminal_command
from src.tools.helpers import format_uptime, get_memory_mb
from src.utils.usage_tracker import record_tool_call

_SERVER_START: float = time.time()
_TECH_STACKS_DIR: Path = TECH_STACKS_DIR
_MCP_ROOT: Path = PROJECT_ROOT


# ---------------------------------------------------------------------------
# Async subprocess helper (DRY)
# ---------------------------------------------------------------------------


async def _async_run(
    *cmd: str,
    cwd: str | None = None,
    timeout: int = 10,
) -> tuple[int, str, str]:
    """Run a command asynchronously.  Returns ``(returncode, stdout, stderr)``.

    Uses ``asyncio.create_subprocess_exec`` so the event loop is never
    blocked — unlike ``subprocess.run`` which freezes the entire server.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
        preexec_fn=os.setsid if sys.platform != "win32" else None,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout,
        )
        return (
            proc.returncode or 0,
            (stdout_bytes or b"").decode("utf-8", errors="replace"),
            (stderr_bytes or b"").decode("utf-8", errors="replace"),
        )
    except asyncio.TimeoutError:
        # Kill entire process group (not just the parent)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, OSError):
            proc.kill()
        await proc.wait()
        return (-1, "", f"Command timed out after {timeout}s")


def register_system_tools(mcp: FastMCP) -> None:
    """Register system-related tools onto the FastMCP instance."""

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
        # Security: log only base command name — full args may contain secrets
        import shlex as _shlex
        try:
            _base_cmd = _shlex.split(command)[0]
        except ValueError:
            _base_cmd = command.split()[0] if command.split() else command
        record_tool_call("run_terminal_command", query=_base_cmd)
        return result

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
        from src.server import __version__

        uptime_sec = time.time() - _SERVER_START

        # ChromaDB status — async HTTP call (non-blocking)
        chroma_status = "not_running"
        try:
            import httpx

            async with httpx.AsyncClient(timeout=2) as client:
                chroma_url = f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat"
                resp = await client.get(chroma_url)
                chroma_status = "running" if resp.status_code == 200 else "error"
        except Exception:
            pass

        # Disk usage (fast I/O — acceptable sync)
        chroma_dir = Path.home() / ".mcp_global_db"
        chroma_size_mb = 0.0
        if chroma_dir.exists():
            _total_bytes = 0
            for _dp, _, _fns in os.walk(chroma_dir):
                for _fn in _fns:
                    try:
                        _total_bytes += os.path.getsize(os.path.join(_dp, _fn))
                    except OSError:
                        pass
            chroma_size_mb = _total_bytes / (1024 * 1024)

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
                "uptime": format_uptime(uptime_sec),
                "uptime_seconds": round(uptime_sec, 1),
                "memory_mb": round(get_memory_mb(), 1),
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
        action = action.strip().lower()

        if action == "status":
            # Try HTTP heartbeat first (async, non-blocking)
            try:
                import httpx

                async with httpx.AsyncClient(timeout=3) as client:
                    chroma_url = f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat"
                    resp = await client.get(chroma_url)
                    heartbeat = resp.json()
                    return json.dumps(
                        {
                            "status": "running",
                            "port": CHROMA_PORT,
                            "heartbeat": heartbeat,
                        },
                        indent=2,
                    )
            except Exception:
                pass

            # Fallback: async lsof
            rc, stdout, _ = await _async_run("lsof", "-i", f":{CHROMA_PORT}", timeout=5)
            if rc == 0 and stdout.strip():
                return json.dumps(
                    {
                        "status": "running",
                        "port": CHROMA_PORT,
                        "details": stdout.strip().split("\n")[:3],
                    },
                    indent=2,
                )

            return json.dumps(
                {
                    "status": "stopped",
                    "message": f"ChromaDB not running on port {CHROMA_PORT}.",
                    "hint": "Use action 'start' to launch it.",
                },
                indent=2,
            )

        elif action == "start":
            # Check if already running
            rc, stdout, _ = await _async_run("lsof", "-i", f":{CHROMA_PORT}", timeout=5)
            if rc == 0 and stdout.strip():
                return json.dumps(
                    {
                        "status": "already_running",
                        "message": f"ChromaDB is already running on port {CHROMA_PORT}.",
                    },
                    indent=2,
                )

            # Find chroma binary
            chroma_bin = str(_MCP_ROOT / ".venv" / "bin" / "chroma")
            if not Path(chroma_bin).exists():
                rc, stdout, _ = await _async_run("which", "chroma", timeout=5)
                chroma_bin = stdout.strip() if rc == 0 else ""

            if not chroma_bin:
                return json.dumps(
                    {
                        "status": "error",
                        "message": "chroma CLI not found. Install: pip install chromadb",
                    },
                    indent=2,
                )

            db_path = str(CHROMA_DB_PATH)
            CHROMA_DB_PATH.mkdir(parents=True, exist_ok=True)

            # Log directory: persistent, with rotation
            from src.config import (
                MCP_LOG_DIR,
                CHROMA_LOG_MAX_BYTES,
                CHROMA_LOG_BACKUP_COUNT,
            )

            MCP_LOG_DIR.mkdir(parents=True, exist_ok=True)

            stdout_log = MCP_LOG_DIR / "chromadb.stdout.log"
            stderr_log = MCP_LOG_DIR / "chromadb.stderr.log"

            # Simple rotation: if log exceeds max size, rotate .log → .1 → .2 → .3
            for log_path in (stdout_log, stderr_log):
                if log_path.exists() and log_path.stat().st_size > CHROMA_LOG_MAX_BYTES:
                    for i in range(CHROMA_LOG_BACKUP_COUNT, 0, -1):
                        dst = log_path.parent / f"{log_path.stem}.{i}{log_path.suffix}"
                        src = (
                            log_path.parent
                            / f"{log_path.stem}.{i - 1}{log_path.suffix}"
                            if i > 1
                            else log_path
                        )
                        if src.exists():
                            dst.unlink(missing_ok=True)
                            src.rename(dst)

            # Start as background process (detached)
            import subprocess

            stdout_f = open(stdout_log, "a", encoding="utf-8")  # noqa: SIM115
            stderr_f = open(stderr_log, "a", encoding="utf-8")  # noqa: SIM115
            subprocess.Popen(
                [chroma_bin, "run", "--path", db_path, "--port", str(CHROMA_PORT)],
                stdout=stdout_f,
                stderr=stderr_f,
                start_new_session=True,
            )
            stdout_f.close()
            stderr_f.close()

            await asyncio.sleep(3)

            # Verify
            rc, stdout, _ = await _async_run("lsof", "-i", f":{CHROMA_PORT}", timeout=5)
            started = rc == 0 and stdout.strip()

            return json.dumps(
                {
                    "status": "started" if started else "failed",
                    "port": CHROMA_PORT,
                    "db_path": db_path,
                    "logs": str(MCP_LOG_DIR),
                    "message": "ChromaDB server launched"
                    if started
                    else f"Check {stderr_log}",
                },
                indent=2,
            )

        elif action == "stop":
            rc, stdout, _ = await _async_run("lsof", "-ti", f":{CHROMA_PORT}", timeout=5)
            pids = stdout.strip().split("\n") if stdout.strip() else []

            if not pids:
                return json.dumps(
                    {
                        "status": "not_running",
                        "message": "ChromaDB is not running.",
                    },
                    indent=2,
                )

            for pid in pids:
                if pid.isdigit():
                    await _async_run("kill", pid, timeout=5)

            await asyncio.sleep(1)

            return json.dumps(
                {
                    "status": "stopped",
                    "killed_pids": pids,
                    "message": "ChromaDB server stopped.",
                },
                indent=2,
            )

        else:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Unknown action: '{action}'",
                    "available_actions": ["start", "stop", "status"],
                },
                indent=2,
            )

    @mcp.tool()
    async def self_update() -> str:
        """Pull latest MCP server code from Git remote.

        Call this tool when user asks to:
        - Update or upgrade the MCP server code
        - Pull latest changes for the MCP server

        Returns:
            JSON with git pull result and restart hint.
        """
        rc, stdout, stderr = await _async_run(
            "git",
            "pull",
            "--rebase",
            cwd=str(_MCP_ROOT),
            timeout=30,
        )

        return json.dumps(
            {
                "status": "success" if rc == 0 else "error",
                "action": "git pull --rebase",
                "stdout": stdout.strip()[-500:],
                "stderr": stderr.strip()[-300:] if rc != 0 else "",
                "hint": "Restart MCP server to apply updates." if rc == 0 else "",
            },
            indent=2,
        )

    @mcp.tool()
    async def backup_memory_database(max_backups: int = 5) -> str:
        """Backup ChromaDB memory database to a compressed archive.

        Call this tool when user asks to:
        - Backup the memory / database / ChromaDB
        - Create a snapshot of the knowledge base
        - Protect against data loss

        Creates a timestamped .tar.gz in ~/.mcp_global_db/backups/.
        Auto-cleans old backups beyond max_backups.

        Args:
            max_backups: Maximum number of backups to keep (default 5).

        Returns:
            JSON with backup path, size, and cleanup info.
        """
        import tarfile
        from datetime import datetime

        db_path = CHROMA_DB_PATH
        backup_dir = db_path / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        if not db_path.exists():
            return json.dumps(
                {
                    "status": "error",
                    "message": f"ChromaDB directory not found: {db_path}",
                },
                indent=2,
            )

        # Create timestamped backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"chromadb_backup_{timestamp}.tar.gz"
        backup_path = backup_dir / backup_name

        try:
            # Compress — exclude backups/ and logs/ from archive
            with tarfile.open(backup_path, "w:gz") as tar:
                for item in db_path.iterdir():
                    if item.name in ("backups", "logs"):
                        continue
                    tar.add(str(item), arcname=item.name)

            backup_size = backup_path.stat().st_size
            size_mb = round(backup_size / (1024 * 1024), 2)

            # Cleanup old backups (keep newest max_backups)
            existing = sorted(
                backup_dir.glob("chromadb_backup_*.tar.gz"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            removed = []
            for old in existing[max_backups:]:
                old.unlink()
                removed.append(old.name)

            record_tool_call("backup_memory_database")
            return json.dumps(
                {
                    "status": "success",
                    "backup_path": str(backup_path),
                    "size_mb": size_mb,
                    "total_backups": min(len(existing), max_backups),
                    "cleaned_up": removed,
                    "message": f"Backup created: {backup_name} ({size_mb} MB)",
                },
                indent=2,
            )

        except Exception as exc:  # noqa: BLE001
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Backup failed: {exc}",
                },
                indent=2,
            )

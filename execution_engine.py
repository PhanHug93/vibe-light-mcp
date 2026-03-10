"""
Execution Engine — Sandboxed Terminal Command Runner.

Provides a standalone async function to execute shell commands with:
  - **Blocklist** filtering for dangerous commands.
  - **Timeout** protection (default 60 s).
  - **Full capture** of stdout, stderr, and exit code.

Architecture: Pure logic — no MCP dependency.
``main.py`` imports and wraps with ``@mcp.tool()``.

Usage::

    from execution_engine import execute_terminal_command

    result = await execute_terminal_command("./gradlew assembleDebug")
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shlex

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Security — Blocklist
# ---------------------------------------------------------------------------

# Dangerous base commands (exact match on first token).
_BLOCKED_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "sudo",
        "su",
        "mkfs",
        "dd",
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
        "init",
        "systemctl",
        "kill",
        "killall",
        "pkill",
        "mount",
        "umount",
        "fdisk",
        "parted",
        "format",
        "curl|bash",
        "wget|bash",
    }
)

# Dangerous argument patterns (anywhere in the command string).
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+.*-\s*[rR]", re.IGNORECASE),       # rm -r / rm -rf
    re.compile(r"\brm\s+.*--recursive", re.IGNORECASE),     # rm --recursive
    re.compile(r"\bchmod\s+777\b"),                          # chmod 777
    re.compile(r"\bchown\b"),                                # chown
    re.compile(r"\bmkfs\b"),                                 # mkfs.*
    re.compile(r"\bdd\s+"),                                  # dd if=...
    re.compile(r">\s*/dev/sd[a-z]"),                         # redirect to disk
    re.compile(r"\b:()\s*\{"),                               # fork bomb :(){ :|:& };:
    re.compile(r"\|.*\bsh\b"),                               # pipe into sh
    re.compile(r"\|.*\bbash\b"),                             # pipe into bash
    re.compile(r"\bsudo\b"),                                 # sudo anywhere
    re.compile(r"\beval\b"),                                 # eval
    re.compile(r"`[^`]+`"),                                  # command substitution backticks
    re.compile(r"\$\("),                                     # command substitution $(...)
]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TIMEOUT: int = 60  # seconds
_MAX_OUTPUT_CHARS: int = 50_000  # truncate huge outputs


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _is_command_safe(command: str) -> str | None:
    """Validate *command* against the blocklist.

    Returns ``None`` if the command is safe, or a rejection reason string.
    """
    stripped = command.strip()
    if not stripped:
        return "Empty command."

    # 1. Check first token against blocked commands.
    try:
        tokens = shlex.split(stripped)
    except ValueError:
        tokens = stripped.split()

    if tokens:
        base_cmd = tokens[0].rsplit("/", maxsplit=1)[-1].lower()
        if base_cmd in _BLOCKED_COMMANDS:
            return f"Blocked command: `{base_cmd}` is on the deny-list."

    # 2. Check full string against dangerous patterns.
    for pattern in _BLOCKED_PATTERNS:
        if pattern.search(stripped):
            return (
                f"Blocked pattern detected: `{pattern.pattern}` "
                f"matched in command."
            )

    return None


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int = _MAX_OUTPUT_CHARS) -> str:
    """Truncate *text* if it exceeds *limit*, appending a notice."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated — {len(text)} chars total]"


async def execute_terminal_command(
    command: str,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Execute a shell command asynchronously with safety checks.

    Args:
        command: The shell command string to execute.
        timeout: Maximum seconds to wait before killing the process
            (default 60).

    Returns:
        JSON string containing ``status``, ``exit_code``, ``stdout``,
        ``stderr``, and the original ``command``.
    """
    # --- Security gate ---
    rejection = _is_command_safe(command)
    if rejection is not None:
        logger.warning("Command rejected: %s — %s", command, rejection)
        return json.dumps(
            {
                "status": "rejected",
                "reason": rejection,
                "command": command,
            },
            indent=2,
            ensure_ascii=False,
        )

    # --- Execute ---
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            logger.warning("Command timed out after %ds: %s", timeout, command)
            return json.dumps(
                {
                    "status": "timeout",
                    "message": f"Process killed after {timeout}s timeout.",
                    "command": command,
                },
                indent=2,
                ensure_ascii=False,
            )

        stdout_str = _truncate(stdout_bytes.decode("utf-8", errors="replace"))
        stderr_str = _truncate(stderr_bytes.decode("utf-8", errors="replace"))
        exit_code = process.returncode or 0

        return json.dumps(
            {
                "status": "success" if exit_code == 0 else "error",
                "exit_code": exit_code,
                "stdout": stdout_str.strip(),
                "stderr": stderr_str.strip(),
                "command": command,
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("execute_terminal_command failed")
        return json.dumps(
            {
                "status": "error",
                "message": f"Execution failed: {exc}",
                "command": command,
            },
            indent=2,
            ensure_ascii=False,
        )

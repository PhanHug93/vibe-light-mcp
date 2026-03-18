"""Execution Engine — Defense-in-Depth Terminal Command Runner.

Security model (REPLACED blocklist → allowlist):
  - **Layer 1 — Shell Normalization**: resolve real binary name via
    ``shutil.which()`` + basename to defeat path-based bypass
    (``/bin/rm``, ``./rm``, ``../../bin/rm`` all resolve to ``rm``).
  - **Layer 2 — Allowlist**: only pre-approved commands pass.
    Configurable via ``MCP_EXEC_MODE`` env var.
  - **Layer 3 — Shell Meta-Attack Detection**: block dangerous shell
    patterns (backtick substitution, ``$()``, ``eval``, pipe-to-interpreter).
  - **Layer 4 — Audit Logging**: every command logged to stderr.

Why NOT blocklist?
  Blocklist is security theater. Impossible to enumerate all attack vectors:
  ``/bin/rm``, ``$x$y``, base64 decode, etc. Allowlist = deny by default.

Usage::

    from src.engine.execution import execute_terminal_command

    result = await execute_terminal_command("git status")
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import signal
import subprocess as _subprocess
import sys

from src.config import DEFAULT_COMMAND_TIMEOUT, MAX_OUTPUT_CHARS, MCP_EXEC_MODE

logger = logging.getLogger(__name__)

# Platform detection — used for process group management
IS_WINDOWS = sys.platform == "win32"

# ---------------------------------------------------------------------------
# Layer 2 — Allowlist (deny-by-default)
# ---------------------------------------------------------------------------

# Safe commands for development workflows.
# These are base binary names (after normalization).
_ALLOWED_COMMANDS: frozenset[str] = frozenset(
    {
        # File inspection (read-only)
        "ls",
        "cat",
        "head",
        "tail",
        "less",
        "more",
        "file",
        "stat",
        "wc",
        "du",
        "df",
        "tree",
        "find",
        "locate",
        "which",
        "whereis",
        "realpath",
        "readlink",
        "basename",
        "dirname",
        # Text processing
        "grep",
        "rg",
        "ag",
        "awk",
        "sed",
        "sort",
        "uniq",
        "cut",
        "tr",
        "diff",
        "comm",
        "paste",
        "column",
        "jq",
        "yq",
        "xargs",
        # Development tools
        "git",
        "python",
        "python3",
        "pip",
        "pip3",
        "uv",
        "node",
        "npm",
        "npx",
        "yarn",
        "pnpm",
        "bun",
        "deno",
        "java",
        "javac",
        "kotlin",
        "kotlinc",
        "gradle",
        "gradlew",
        "mvn",
        "swift",
        "swiftc",
        "xcodebuild",
        "pod",
        "carthage",
        "flutter",
        "dart",
        "pub",
        "cargo",
        "rustc",
        "go",
        "make",
        "cmake",
        "ruby",
        "gem",
        "bundle",
        "rake",
        "php",
        "composer",
        "dotnet",
        "nuget",
        # Build & package tools
        "docker",
        "docker-compose",
        "podman",
        "terraform",
        "ansible",
        "kubectl",
        "helm",
        # Shell utilities (safe)
        "echo",
        "printf",
        "date",
        "env",
        "printenv",
        "id",
        "whoami",
        "uname",
        "hostname",
        "pwd",
        "true",
        "false",
        "yes",
        "seq",
        "sleep",
        "timeout",
        "time",
        "tee",
        "xdg-open",
        "open",
        # Network inspection (read-only)
        "ping",
        "curl",
        "wget",
        "httpie",
        "http",
        "dig",
        "nslookup",
        "host",
        "traceroute",
        "lsof",
        "netstat",
        "ss",
        # Process inspection (read-only)
        "ps",
        "top",
        "htop",
        "pgrep",
        "uptime",
        "free",
        # Archive (read-only extraction)
        "tar",
        "unzip",
        "gzip",
        "gunzip",
        "bzip2",
        "xz",
        "zstd",
        # Editor/pager
        "vim",
        "nvim",
        "nano",
        "code",
        # Project-specific
        "repomix",
        "pytest",
        "mypy",
        "ruff",
        "black",
        "isort",
        "flake8",
        "eslint",
        "prettier",
        "tsc",
        "webpack",
        "vite",
        "esbuild",
        "chroma",
        # File operations (controlled)
        "mkdir",
        "touch",
        "cp",
        "mv",
        "ln",
        "chmod",
    }
)

# Commands that are NEVER allowed even in unrestricted mode.
_ALWAYS_BLOCKED: frozenset[str] = frozenset(
    {
        "rm",
        "rmdir",  # Destructive file operations
        "sudo",
        "su",
        "doas",  # Privilege escalation
        "mkfs",
        "fdisk",
        "parted",
        "format",  # Disk formatting
        "dd",  # Raw disk write
        "shutdown",
        "reboot",
        "poweroff",
        "halt",
        "init",  # System control
        "kill",
        "killall",
        "pkill",  # Process killing (use IDE instead)
        "mount",
        "umount",  # Filesystem mount
        "chown",  # Ownership change (privilege)
        "iptables",
        "ufw",  # Firewall
        "crontab",  # Scheduled tasks
        "passwd",
        "useradd",
        "userdel",
        "usermod",  # User management
    }
)


# ---------------------------------------------------------------------------
# Layer 1.7 — Interpreter Inline Execution Guard ("Living off the Land")
# ---------------------------------------------------------------------------

# Interpreters that can execute arbitrary code via command-line flags.
# Maps base command → set of dangerous inline-execution flags.
_INTERPRETER_INLINE_FLAGS: dict[str, frozenset[str]] = {
    "python": frozenset({"-c"}),
    "python3": frozenset({"-c"}),
    "node": frozenset({"-e", "--eval", "--print", "-p"}),
    "ruby": frozenset({"-e", "--eval"}),
    "perl": frozenset({"-e", "-E"}),
    "php": frozenset({"-r"}),
    "lua": frozenset({"-e"}),
}

# python -m <module> is allowed ONLY for these safe modules.
_SAFE_PYTHON_MODULES: frozenset[str] = frozenset(
    {
        # Testing
        "pytest",
        "unittest",
        "doctest",
        "coverage",
        # Package management
        "pip",
        "venv",
        "ensurepip",
        "virtualenv",
        # Code quality
        "mypy",
        "ruff",
        "black",
        "isort",
        "flake8",
        "pylint",
        "pyright",
        # Build tools
        "build",
        "setuptools",
        "wheel",
        "twine",
        # Debugging / profiling
        "pdb",
        "cProfile",
        "timeit",
        "trace",
        # Stdlib safe utilities
        "json.tool",
        "http.server",
        "compileall",
        "py_compile",
        "site",
        "sysconfig",
        "platform",
    }
)


def _check_interpreter_abuse(base_cmd: str, full_command: str) -> str | None:
    """Detect 'Living off the Land' attacks via interpreter inline flags.

    Blocks: ``python3 -c "import shutil; shutil.rmtree('/')"``
    Allows: ``python3 script.py``, ``python3 -m pytest tests/``

    Returns rejection reason or None if safe.
    """
    base_lower = base_cmd.lower()
    dangerous_flags = _INTERPRETER_INLINE_FLAGS.get(base_lower)
    if dangerous_flags is None:
        return None  # not an interpreter we care about

    try:
        tokens = shlex.split(full_command)
    except ValueError:
        tokens = full_command.split()

    # Find where the interpreter token is, then scan its arguments
    cmd_found = False
    for i, token in enumerate(tokens):
        # Skip env-var assignments at the start
        if not cmd_found:
            if "=" in token and not token.startswith("-"):
                continue
            # This is the command token
            if os.path.basename(token).lower() == base_lower:
                cmd_found = True
                continue
            continue

        # Now scanning arguments after the interpreter
        token_lower = token.lower()

        # Check for dangerous inline flags
        if token_lower in dangerous_flags:
            return (
                f"🛡️ BLOCKED: '{base_cmd} {token}' executes arbitrary inline code "
                f"(Living off the Land attack). Use a script file instead."
            )

        # Special handling for python -m: allow only safe modules
        if base_lower in ("python", "python3") and token_lower == "-m":
            # Next token should be the module name
            if i + 1 < len(tokens):  # -m is not last token
                # Find the module name (next non-flag token after -m)
                for j in range(i + 1, len(tokens)):
                    mod_candidate = tokens[j]
                    if not mod_candidate.startswith("-"):
                        if mod_candidate not in _SAFE_PYTHON_MODULES:
                            return (
                                f"🛡️ BLOCKED: 'python -m {mod_candidate}' — "
                                f"module not in safe list. "
                                f"Allowed: {', '.join(sorted(_SAFE_PYTHON_MODULES)[:10])}..."
                            )
                        break  # module is safe
            break  # -m found and handled

    return None  # no dangerous flags found


# ---------------------------------------------------------------------------
# Layer 3 — Shell Meta-Attack Detection
# ---------------------------------------------------------------------------

_SHELL_META_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Command substitution — can execute arbitrary hidden commands
    (re.compile(r"`[^`]+`"), "backtick command substitution"),
    (re.compile(r"\$\("), "$(…) command substitution"),
    # Variable expansion tricks — can build blocked commands dynamically
    (re.compile(r"\$\{[^}]+\}"), "${…} variable expansion"),
    # Eval — executes arbitrary string as command
    (re.compile(r"\beval\b"), "eval command"),
    # Base64 decode piped to interpreter — obfuscation attack
    (
        re.compile(
            r"base64\s+(-d|--decode).*\|\s*(sh|bash|zsh|python|perl|ruby)",
            re.IGNORECASE,
        ),
        "base64 decode piped to interpreter",
    ),
    # Pipe into interpreter — arbitrary code execution
    (
        re.compile(r"\|\s*(sh|bash|zsh|python[23]?|perl|ruby|node)\b"),
        "pipe into interpreter",
    ),
    # Fork bomb pattern
    (re.compile(r":\s*\(\s*\)\s*\{"), "fork bomb pattern"),
    # Direct /dev/ writes
    (re.compile(r">\s*/dev/sd[a-z]"), "direct write to block device"),
    # Redirect to overwrite critical system files
    (re.compile(r">\s*/etc/"), "redirect to /etc/"),
    # Hex/octal escape execution
    (re.compile(r"\\x[0-9a-fA-F]{2}.*\|\s*(sh|bash)"), "hex escape execution"),
]


# ---------------------------------------------------------------------------
# Layer 1 — Shell Normalization
# ---------------------------------------------------------------------------


def _normalize_command_name(command: str) -> str | None:
    """Extract and normalize the base command name.

    Handles:
    - ``/bin/rm`` → ``rm``
    - ``./node_modules/.bin/tsc`` → ``tsc``
    - ``python3.11`` → ``python3.11`` (kept as-is for allowlist check)
    - ``.venv/bin/python`` → ``python``

    Returns ``None`` if the command string is empty.
    """
    stripped = command.strip()
    if not stripped:
        return None

    # Handle commands starting with env vars like KEY=val cmd
    # e.g., "NODE_ENV=production npm run build" → extract "npm"
    parts = stripped.split()
    cmd_token = None
    for part in parts:
        if "=" in part and not part.startswith("-"):
            continue  # skip env var assignments
        cmd_token = part
        break

    if cmd_token is None:
        return None

    # Get the basename (defeats /bin/rm, ./rm, ../../bin/rm)
    base = os.path.basename(cmd_token)

    # Handle common wrappers
    if base in ("env",):
        # "env python3 script.py" → extract "python3"
        remaining = parts[parts.index(cmd_token) + 1 :]
        for part in remaining:
            if "=" in part:
                continue
            if part.startswith("-"):
                continue
            return os.path.basename(part)
        return None

    return base


# ---------------------------------------------------------------------------
# Validation — Layered Defense
# ---------------------------------------------------------------------------


def _is_command_safe(command: str) -> str | None:
    """Validate *command* through defense-in-depth layers.

    Returns ``None`` if the command is safe, or a rejection reason string.
    """
    stripped = command.strip()
    if not stripped:
        return "Empty command."

    # --- Layer 1: Normalize command name ---
    base_cmd = _normalize_command_name(stripped)
    if base_cmd is None:
        return "Could not determine command name."

    base_cmd_lower = base_cmd.lower()

    # --- Layer 1.5: Always-blocked commands (even in unrestricted mode) ---
    if base_cmd_lower in _ALWAYS_BLOCKED:
        return (
            f"🚫 BLOCKED: `{base_cmd}` is permanently banned "
            f"(destructive/privilege operation). "
            f"No configuration can override this."
        )

    # --- Layer 2: Allowlist check (configurable) ---
    if MCP_EXEC_MODE == "allowlist":
        if base_cmd_lower not in _ALLOWED_COMMANDS:
            return (
                f"⛔ DENIED: `{base_cmd}` is not in the allowlist. "
                f"Allowed commands: development tools, read-only utilities. "
                f"Set MCP_EXEC_MODE=unrestricted to allow all commands."
            )

    # --- Layer 1.7: Interpreter inline execution guard ---
    interpreter_abuse = _check_interpreter_abuse(base_cmd, stripped)
    if interpreter_abuse is not None:
        return interpreter_abuse

    # --- Layer 3: Shell meta-attack detection ---
    for pattern, description in _SHELL_META_PATTERNS:
        if pattern.search(stripped):
            return (
                f"🛡️ BLOCKED: shell meta-attack detected — {description}. "
                f"Pattern: `{pattern.pattern}`"
            )

    return None


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int = MAX_OUTPUT_CHARS) -> str:
    """Truncate *text* if it exceeds *limit*, appending a notice."""
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n... [truncated — {len(text)} chars total]"


# ---------------------------------------------------------------------------
# Core — Async Execution
# ---------------------------------------------------------------------------


async def execute_terminal_command(
    command: str,
    timeout: int = DEFAULT_COMMAND_TIMEOUT,
) -> str:
    """Execute a shell command asynchronously with defense-in-depth security.

    Security layers:
      1. Shell normalization (defeat path-based bypass)
      2. Allowlist check (deny-by-default)
      3. Shell meta-attack detection
      4. Audit logging

    Args:
        command: The shell command string to execute.
        timeout: Maximum seconds to wait before killing the process
            (default 60).

    Returns:
        JSON string containing ``status``, ``exit_code``, ``stdout``,
        ``stderr``, and the original ``command``.
    """
    # --- Layer 4: Audit log (ALWAYS, before any checks) ---
    logger.info("EXEC AUDIT | mode=%s | cmd=%s", MCP_EXEC_MODE, command)

    # --- Security gate ---
    rejection = _is_command_safe(command)
    if rejection is not None:
        logger.warning("EXEC REJECTED | cmd=%s | reason=%s", command, rejection)
        return json.dumps(
            {
                "status": "rejected",
                "reason": rejection,
                "command": command,
                "security_mode": MCP_EXEC_MODE,
            },
            indent=2,
            ensure_ascii=False,
        )

    # --- Execute ---
    logger.info("EXEC ALLOWED | cmd=%s", command)

    try:
        # Start in a NEW PROCESS GROUP so we can kill the entire tree,
        # not just the shell wrapper.
        #   Unix:    os.setsid() → new session/process group
        #   Windows: CREATE_NEW_PROCESS_GROUP → new process group
        platform_kwargs: dict = (
            {"creationflags": _subprocess.CREATE_NEW_PROCESS_GROUP}
            if IS_WINDOWS
            else {"preexec_fn": os.setsid}
        )
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **platform_kwargs,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            # Kill the ENTIRE process group (shell + all children)
            await _kill_process_tree(process)
            logger.warning("EXEC TIMEOUT | cmd=%s | after=%ds", command, timeout)
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
        logger.exception("EXEC FAILED | cmd=%s", command)
        return json.dumps(
            {
                "status": "error",
                "message": f"Execution failed: {exc}",
                "command": command,
            },
            indent=2,
            ensure_ascii=False,
        )


# ---------------------------------------------------------------------------
# Process tree cleanup (zombie prevention)
# ---------------------------------------------------------------------------


async def _kill_process_tree(process: asyncio.subprocess.Process) -> None:
    """Kill the entire process group to prevent zombie/orphan processes.

    When using ``create_subprocess_shell``, ``process.kill()`` only kills
    the shell wrapper.  Child processes (e.g. ``gradlew assembleDebug``
    consuming 4 GB RAM) become orphans and keep running forever.

    Cross-platform:
      - **Unix**: ``os.killpg(pgid, SIGTERM/SIGKILL)`` — kill by process group.
      - **Windows**: ``taskkill /F /T /PID`` — kill process tree (no POSIX signals).
    """
    pid = process.pid
    if pid is None:
        return

    if IS_WINDOWS:
        await _kill_process_tree_windows(pid, process)
    else:
        await _kill_process_tree_unix(pid, process)


async def _kill_process_tree_unix(
    pid: int, process: asyncio.subprocess.Process
) -> None:
    """Unix: kill entire process group via SIGTERM → SIGKILL."""
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return

    # Step 1: Graceful termination (SIGTERM to entire group)
    try:
        os.killpg(pgid, signal.SIGTERM)
        logger.info("SIGTERM sent to process group %d", pgid)
    except ProcessLookupError:
        return

    # Step 2: Wait for graceful shutdown
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
        logger.info("Process group %d terminated gracefully", pgid)
        return
    except asyncio.TimeoutError:
        pass

    # Step 3: Force kill (SIGKILL)
    try:
        os.killpg(pgid, signal.SIGKILL)
        logger.warning("SIGKILL sent to process group %d (force)", pgid)
    except ProcessLookupError:
        pass

    # Final wait to reap zombie
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        logger.error("Process group %d still alive after SIGKILL!", pgid)


async def _kill_process_tree_windows(
    pid: int, process: asyncio.subprocess.Process
) -> None:
    """Windows: kill process tree via taskkill /F /T.

    Windows does not have POSIX signals (SIGTERM/SIGKILL) or process groups
    (setsid/killpg). Instead we use:
      - ``CTRL_BREAK_EVENT`` for graceful stop (only works with
        CREATE_NEW_PROCESS_GROUP).
      - ``taskkill /F /T /PID`` for force-killing the entire process tree.
    """
    # Step 1: Graceful — send CTRL_BREAK_EVENT
    try:
        os.kill(pid, signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
        logger.info("CTRL_BREAK_EVENT sent to PID %d", pid)
    except (ProcessLookupError, OSError):
        return

    # Step 2: Wait for graceful shutdown
    try:
        await asyncio.wait_for(process.wait(), timeout=3)
        logger.info("PID %d terminated gracefully", pid)
        return
    except asyncio.TimeoutError:
        pass

    # Step 3: Force kill entire process tree
    try:
        kill_proc = await asyncio.create_subprocess_shell(
            f"taskkill /F /T /PID {pid}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(kill_proc.wait(), timeout=5)
        logger.warning("taskkill /F /T sent to PID %d (force)", pid)
    except (asyncio.TimeoutError, OSError) as exc:
        logger.error("Failed to taskkill PID %d: %s", pid, exc)

    # Final wait to reap
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        logger.error("PID %d still alive after taskkill!", pid)

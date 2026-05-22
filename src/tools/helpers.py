"""Shared helper functions used across multiple tool modules.

Extracted from ``server.py`` for SRP compliance.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

# ---------------------------------------------------------------------------
# Workspace ID
# ---------------------------------------------------------------------------

WORKSPACE_ERROR_MSG: str = (
    "ERROR: workspace_path is REQUIRED. You MUST provide the absolute path "
    "of the project root directory (e.g. /Users/admin/projects/my-app). "
    "Infer this from the file paths the user is currently editing. "
    "DO NOT leave this empty — call this tool again with workspace_path filled in."
)


def make_workspace_id(workspace_path: str) -> str:
    """Generate deterministic workspace ID from an explicit project path.

    **Path normalization** (prevents hash fragmentation):
      - ``~/projects/foo`` → ``/Users/admin/projects/foo``
      - ``/projects/foo/`` → ``/projects/foo``  (strip trailing slash)
      - ``/projects/./foo/../foo`` → ``/projects/foo``  (resolve)
      - On Windows: case-folded (``C:\\Foo`` == ``c:\\foo``)

    Raises *ValueError* if *workspace_path* is empty.
    """
    if not workspace_path or not workspace_path.strip():
        raise ValueError(WORKSPACE_ERROR_MSG)

    # Normalize: expanduser → resolve → strip trailing sep → consistent case
    normalized = str(Path(workspace_path.strip()).expanduser().resolve())
    # On Windows, paths are case-insensitive
    if os.name == "nt":
        normalized = normalized.lower()

    return hashlib.md5(normalized.encode()).hexdigest()[:8]  # noqa: S324


# ---------------------------------------------------------------------------
# Server diagnostics
# ---------------------------------------------------------------------------


def format_uptime(seconds: float) -> str:
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


def get_memory_mb() -> float:
    """Get current process RSS memory in MB (macOS/Linux).

    ``ru_maxrss`` units vary by platform:
      - macOS: bytes
      - Linux: kilobytes
    """
    try:
        import resource
        import sys as _sys

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if _sys.platform == "darwin":
            return rss / (1024 * 1024)  # macOS: bytes → MB
        return rss / 1024  # Linux: KB → MB
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")
_MEMORY_SCOPES: frozenset[str] = frozenset({"workspace", "session", "global"})


def validate_path_within(path: Path, root: Path) -> Path:
    """Resolve *path* and verify it stays within *root*.

    Prevents path traversal attacks like ``../../config.py``.

    Raises:
        ValueError: If the resolved path escapes *root*.
    """
    resolved = path.resolve()
    root_resolved = root.resolve()
    if (
        not str(resolved).startswith(str(root_resolved) + os.sep)
        and resolved != root_resolved
    ):
        raise ValueError(
            f"Path traversal detected: '{path}' resolves outside '{root}'."
        )
    return resolved


def validate_stack_name(stack: str) -> str | None:
    """Validate a tech stack name.  Returns error message or None if OK.

    Stack names must be alphanumeric + underscore/dash/dot only.
    Prevents directory traversal via stack parameter.
    """
    if not stack or not stack.strip():
        return "Stack name is empty."
    if not _SAFE_NAME_RE.match(stack.strip()):
        return (
            f"Invalid stack name: '{stack}'. "
            "Must contain only letters, digits, underscores, dashes, or dots."
        )
    return None


def validate_memory_scope(scope: str, allow_global: bool = True) -> str | None:
    """Validate a memory scope value. Returns error message or None if OK."""
    normalized = scope.strip().lower()
    allowed = _MEMORY_SCOPES if allow_global else frozenset({"workspace", "session"})
    if normalized not in allowed:
        allowed_text = ", ".join(sorted(allowed))
        return (
            f"Invalid memory_scope: '{scope}'. "
            f"Use one of: {allowed_text}."
        )
    return None


def validate_session_scope_inputs(agent_id: str, session_id: str = "") -> str | None:
    """Validate identifiers used for session-scoped memory isolation."""
    normalized_agent = agent_id.strip()
    if not normalized_agent:
        return (
            "session scope requires a non-empty agent_id for multi-agent isolation. "
            "session_id is optional."
        )
    # session_id is optional by design; if present, caller can use it as a sub-scope.
    _ = session_id.strip()
    return None


def make_session_namespace(
    workspace_path: str,
    agent_id: str = "",
    session_id: str = "",
) -> str:
    """Generate a deterministic session namespace for multi-agent isolation.

    The namespace is stable across repeated calls with the same workspace,
    agent_id, and session_id, but isolated from other agents/sessions.
    ``agent_id`` is REQUIRED for safe multi-agent isolation.
    ``session_id`` is optional and can be used as a finer discriminator.
    """
    ws_id = make_workspace_id(workspace_path)
    normalized_agent = agent_id.strip()
    normalized_session = session_id.strip()
    if not normalized_agent:
        raise ValueError(
            "session scope requires a non-empty agent_id for multi-agent isolation."
        )

    seed = f"{ws_id}:{normalized_agent}:{normalized_session}"
    return hashlib.md5(seed.encode()).hexdigest()[:12]  # noqa: S324

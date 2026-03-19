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
    """Get current process RSS memory in MB (macOS/Linux)."""
    try:
        import resource

        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return rss / (1024 * 1024)  # bytes → MB on macOS
    except Exception:  # noqa: BLE001
        return 0.0


# ---------------------------------------------------------------------------
# Security helpers
# ---------------------------------------------------------------------------


_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9_.-]+$")


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

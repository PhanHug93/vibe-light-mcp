"""
Knowledge Updater — Git-Backed Knowledge Registry Sync.

Synchronises the local ``tech_stacks/`` directory with a remote Git
repository, enabling over-the-air updates to rules & skills files.

Architecture: Pure logic — no MCP dependency.
``main.py`` imports and wraps with ``@mcp.tool()``.

⚠ Security: ALL git commands use ``create_subprocess_exec`` (argument list,
NO shell) to prevent command injection via ``repo_url``.  The URL is also
validated to start with ``https://`` or ``git@``.

Usage::

    from src.engine.knowledge import sync_knowledge_from_git

    result = await sync_knowledge_from_git(
        "https://github.com/user/mcp-knowledge.git"
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------

from src.config import PROJECT_ROOT, TECH_STACKS_DIR

logger = logging.getLogger(__name__)

_BASE_DIR: Path = PROJECT_ROOT
_TECH_STACKS_DIR: Path = TECH_STACKS_DIR
_COMMAND_TIMEOUT: int = 120  # generous for large repos / slow networks

# Allowed URL patterns (security: reject anything else)
_VALID_URL_RE = re.compile(
    r"^(https?://[^\s;|&`$]+|git@[^\s;|&`$]+)$"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_repo_url(repo_url: str) -> str | None:
    """Validate repo_url format.  Returns error message or None if OK."""
    stripped = repo_url.strip()
    if not stripped:
        return "repo_url is empty."
    if not _VALID_URL_RE.match(stripped):
        return (
            f"Invalid repo_url format: '{stripped}'. "
            "Must start with https:// or git@ and contain no shell meta-characters."
        )
    return None


async def _run_git(
    *args: str,
    cwd: Path | None = None,
    timeout: int = _COMMAND_TIMEOUT,
) -> tuple[int, str, str]:
    """Run a git command safely using exec (NO shell).

    Returns ``(exit_code, stdout, stderr)``.
    Uses ``create_subprocess_exec`` to eliminate shell injection.
    """
    process = await asyncio.create_subprocess_exec(
        "git", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(cwd) if cwd else None,
    )
    stdout_bytes, stderr_bytes = await asyncio.wait_for(
        process.communicate(),
        timeout=timeout,
    )
    return (
        process.returncode or 0,
        stdout_bytes.decode("utf-8", errors="replace").strip(),
        stderr_bytes.decode("utf-8", errors="replace").strip(),
    )


def _is_git_repo(path: Path) -> bool:
    """Check if *path* contains a ``.git`` directory."""
    return (path / ".git").is_dir()


# ---------------------------------------------------------------------------
# Core function
# ---------------------------------------------------------------------------


async def sync_knowledge_from_git(repo_url: str) -> str:
    """Synchronise ``tech_stacks/`` with a remote Git repository.

    Strategy:
      1. Validate ``repo_url`` format (reject injection attempts).
      2. If ``tech_stacks/`` is **not** a git repo → delete it and ``git clone``.
      3. If it **is** a git repo → ``git pull --rebase``.
      4. On pull conflict → force-reset to ``origin/main``.
      5. Network / timeout errors are caught and reported gracefully.

    Args:
        repo_url: HTTPS or SSH URL of the Git repository that contains
            the ``tech_stacks/`` content at its root.

    Returns:
        JSON string reporting the sync outcome.
    """
    # --- Security gate: validate URL format ---
    url_error = _validate_repo_url(repo_url)
    if url_error is not None:
        return json.dumps(
            {
                "status": "rejected",
                "reason": url_error,
                "repo_url": repo_url,
            },
            indent=2,
            ensure_ascii=False,
        )

    try:
        # ------------------------------------------------------------------
        # Case 1: Fresh clone
        # ------------------------------------------------------------------
        if not _TECH_STACKS_DIR.exists() or not _is_git_repo(_TECH_STACKS_DIR):
            logger.info("No existing git repo — performing fresh clone.")

            # Remove stale directory (non-git leftovers).
            if _TECH_STACKS_DIR.exists():
                shutil.rmtree(_TECH_STACKS_DIR)

            code, stdout, stderr = await _run_git(
                "clone", repo_url, str(_TECH_STACKS_DIR),
                cwd=_BASE_DIR,
            )

            if code != 0:
                return json.dumps(
                    {
                        "status": "error",
                        "action": "clone",
                        "exit_code": code,
                        "message": stderr or stdout,
                    },
                    indent=2,
                    ensure_ascii=False,
                )

            return json.dumps(
                {
                    "status": "success",
                    "action": "clone",
                    "message": f"Cloned {repo_url} into tech_stacks/.",
                    "details": stdout or stderr,
                },
                indent=2,
                ensure_ascii=False,
            )

        # ------------------------------------------------------------------
        # Case 2: Pull (with rebase)
        # ------------------------------------------------------------------
        logger.info("Existing git repo found — pulling latest changes.")

        code, stdout, stderr = await _run_git(
            "pull", "origin", "main", "--rebase",
            cwd=_TECH_STACKS_DIR,
        )

        if code == 0:
            return json.dumps(
                {
                    "status": "success",
                    "action": "pull",
                    "message": "Knowledge base updated successfully.",
                    "details": stdout or stderr,
                },
                indent=2,
                ensure_ascii=False,
            )

        # ------------------------------------------------------------------
        # Case 3: Conflict → force-reset to origin/main
        # ------------------------------------------------------------------
        logger.warning("Pull failed (code=%d) — attempting force reset.", code)

        reset_steps = [
            ("rebase", "--abort"),
            ("fetch", "--all"),
            ("reset", "--hard", "origin/main"),
            ("clean", "-fd"),
        ]
        for step_args in reset_steps:
            rc, out, err = await _run_git(*step_args, cwd=_TECH_STACKS_DIR)
            if rc != 0 and step_args[0] != "rebase":
                logger.warning("Reset step failed: %s → %s", step_args, err)

        return json.dumps(
            {
                "status": "success",
                "action": "force_reset",
                "message": "Conflict detected — force-reset to origin/main.",
                "details": "Local changes discarded, now matching remote HEAD.",
            },
            indent=2,
            ensure_ascii=False,
        )

    except asyncio.TimeoutError:
        logger.error("Git operation timed out after %ds.", _COMMAND_TIMEOUT)
        return json.dumps(
            {
                "status": "error",
                "action": "timeout",
                "message": f"Git operation timed out after {_COMMAND_TIMEOUT}s. "
                "Check your network connection.",
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("sync_knowledge_from_git failed")
        return json.dumps(
            {
                "status": "error",
                "action": "exception",
                "message": str(exc),
            },
            indent=2,
            ensure_ascii=False,
        )

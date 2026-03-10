"""
Knowledge Updater — Git-Backed Knowledge Registry Sync.

Synchronises the local ``tech_stacks/`` directory with a remote Git
repository, enabling over-the-air updates to rules & skills files.

Architecture: Pure logic — no MCP dependency.
``main.py`` imports and wraps with ``@mcp.tool()``.

Usage::

    from knowledge_updater import sync_knowledge_from_git

    result = await sync_knowledge_from_git(
        "https://github.com/user/mcp-knowledge.git"
    )
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging & Constants
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

_BASE_DIR: Path = Path(__file__).resolve().parent
_TECH_STACKS_DIR: Path = _BASE_DIR / "tech_stacks"
_COMMAND_TIMEOUT: int = 120  # generous for large repos / slow networks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _run(
    cmd: str,
    cwd: Path | None = None,
    timeout: int = _COMMAND_TIMEOUT,
) -> tuple[int, str, str]:
    """Run a shell command and return ``(exit_code, stdout, stderr)``.

    Raises ``asyncio.TimeoutError`` if the command exceeds *timeout*.
    """
    process = await asyncio.create_subprocess_shell(
        cmd,
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
      1. If ``tech_stacks/`` is **not** a git repo → delete it and ``git clone``.
      2. If it **is** a git repo → ``git pull --rebase``.
      3. On pull conflict → force-reset to ``origin/main``.
      4. Network / timeout errors are caught and reported gracefully.

    Args:
        repo_url: HTTPS or SSH URL of the Git repository that contains
            the ``tech_stacks/`` content at its root.

    Returns:
        JSON string reporting the sync outcome.
    """
    try:
        # ------------------------------------------------------------------
        # Case 1: Fresh clone
        # ------------------------------------------------------------------
        if not _TECH_STACKS_DIR.exists() or not _is_git_repo(_TECH_STACKS_DIR):
            logger.info("No existing git repo — performing fresh clone.")

            # Remove stale directory (non-git leftovers).
            if _TECH_STACKS_DIR.exists():
                shutil.rmtree(_TECH_STACKS_DIR)

            cmd = f"git clone {repo_url} {_TECH_STACKS_DIR}"
            code, stdout, stderr = await _run(cmd, cwd=_BASE_DIR)

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

        cmd_pull = "git pull origin main --rebase"
        code, stdout, stderr = await _run(cmd_pull, cwd=_TECH_STACKS_DIR)

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

        cmds = [
            "git rebase --abort",                  # clean up any in-progress rebase
            "git fetch --all",                     # fetch latest refs
            "git reset --hard origin/main",        # force-align to remote
            "git clean -fd",                       # remove untracked files
        ]
        for reset_cmd in cmds:
            rc, out, err = await _run(reset_cmd, cwd=_TECH_STACKS_DIR)
            # rebase --abort may fail if no rebase in progress — that's fine
            if rc != 0 and reset_cmd != "git rebase --abort":
                logger.warning("Reset step failed: %s → %s", reset_cmd, err)

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

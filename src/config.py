"""Centralized configuration for vibe-light-mcp.

All hardcoded constants and environment-overridable settings live here.
Other modules import from this single source of truth.

Usage::

    from src.config import CHROMA_HOST, CHROMA_PORT, PROJECT_ROOT
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
"""Absolute path to the project root directory."""

TECH_STACKS_DIR: Path = PROJECT_ROOT / "tech_stacks"
"""Directory containing tech stack knowledge (rules, skills, references)."""

USAGE_LOG_DIR: Path = PROJECT_ROOT / ".usage_logs"
"""Directory for daily usage analytics JSON files."""

# ---------------------------------------------------------------------------
# ChromaDB
# ---------------------------------------------------------------------------

CHROMA_HOST: str = os.getenv("MCP_CHROMA_HOST", "localhost")
CHROMA_PORT: int = int(os.getenv("MCP_CHROMA_PORT", "8888"))
CHROMA_DB_PATH: Path = Path(
    os.getenv("MCP_CHROMA_DB", str(Path.home() / ".mcp_global_db"))
).expanduser()

CHROMA_CONNECT_TIMEOUT: int = 5   # seconds — initial connection + heartbeat
CHROMA_OP_TIMEOUT: int = 15       # seconds — per ChromaDB operation
CHROMA_POOL_SIZE: int = 4         # dedicated thread-pool workers
CHROMA_HEARTBEAT_INTERVAL: int = 30  # seconds — proactive staleness check

# ---------------------------------------------------------------------------
# Logging (ChromaDB + MCP Server)
# ---------------------------------------------------------------------------

MCP_LOG_DIR: Path = CHROMA_DB_PATH / "logs"
"""Persistent log directory for ChromaDB and MCP server logs."""

CHROMA_LOG_MAX_BYTES: int = 5 * 1024 * 1024  # 5 MB per log file
CHROMA_LOG_BACKUP_COUNT: int = 3              # keep 3 rotated backups

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

EMBEDDING_MODEL: str = "all-MiniLM-L12-v2"  # 384d, 12 layers

# ---------------------------------------------------------------------------
# L1/L2 Memory
# ---------------------------------------------------------------------------

L1_PREFIX: str = "mcp_local_"
L2_COLLECTION: str = "mcp_global_knowledge"
L1_TTL_DAYS: int = 3  # auto-cleanup threshold

# ---------------------------------------------------------------------------
# Quick Recall
# ---------------------------------------------------------------------------

QUICK_RECALL_TIMEOUT: int = 5     # seconds — fast timeout for auto-recall
QUICK_RECALL_MAX_CHARS: int = 3000  # truncate auto-recall output

# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

DEFAULT_COMMAND_TIMEOUT: int = 60  # seconds
MAX_OUTPUT_CHARS: int = 50_000     # truncate huge outputs

MCP_EXEC_MODE: str = os.getenv("MCP_EXEC_MODE", "allowlist")
"""Execution security mode:
- ``allowlist``    — only pre-approved commands (default, production-safe)
- ``unrestricted`` — all commands allowed (trusted dev environments only)
"""

# ---------------------------------------------------------------------------
# Usage Tracker
# ---------------------------------------------------------------------------

SIMILARITY_THRESHOLD: float = 0.7  # queries >=70% similar → "repeated"
SIMILARITY_WINDOW: int = 20        # compare only last N queries
FLUSH_SIZE: int = 10               # flush buffer after N entries

# ---------------------------------------------------------------------------
# MCP Server Transport
# ---------------------------------------------------------------------------

MCP_TRANSPORT: str = os.getenv("MCP_TRANSPORT", "stdio")
"""Transport protocol: ``stdio`` | ``sse`` | ``streamable-http``."""

MCP_HOST: str = os.getenv("MCP_HOST", "127.0.0.1")
"""Bind address for SSE / Streamable HTTP server."""

MCP_PORT: int = int(os.getenv("MCP_PORT", "8000"))
"""Listen port for SSE / Streamable HTTP server."""

# ---------------------------------------------------------------------------
# Singleton Lock (SSE / Streamable HTTP only)
# ---------------------------------------------------------------------------

MCP_LOCK_FILE: Path = Path(
    os.getenv("MCP_LOCK_FILE", str(Path.home() / ".mcp_server.lock"))
).expanduser()
"""Lock file to prevent multiple SSE/HTTP server instances on the same port."""

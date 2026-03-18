"""TechStackLocalMCP — Server Orchestrator.

Boots a FastMCP server exposing tools organized by domain:

  - **Workspace**: analyze_workspace, read_reference
  - **Memory**: store_working_context, store_knowledge, search_memory,
    auto_recall, cleanup_workspace, memory_stats
  - **System**: run_terminal_command, server_health, manage_chroma, self_update
  - **Knowledge**: sync_knowledge, update_tech_stack, usage_stats

Architecture (SOLID):
  - This file is a **thin orchestrator** — it creates the FastMCP instance,
    sets up logging, and delegates tool registration to ``src/tools/``.
  - All business logic lives in ``src/engine/`` and ``src/db/``.
  - All tool handlers live in ``src/tools/``.
"""
from __future__ import annotations

__version__: str = "1.0.9"

import logging
import sys

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Logging — CRITICAL: never write to stdout (stdio transport)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# FastMCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("TechStackLocalMCP")

# ---------------------------------------------------------------------------
# Register all tools (domain-organized)
# ---------------------------------------------------------------------------

from src.tools.workspace import register_workspace_tools  # noqa: E402
from src.tools.memory import register_memory_tools  # noqa: E402
from src.tools.system import register_system_tools  # noqa: E402
from src.tools.knowledge import register_knowledge_tools  # noqa: E402

register_workspace_tools(mcp)
register_memory_tools(mcp)
register_system_tools(mcp)
register_knowledge_tools(mcp)

logger.info("All tools registered — 14 tools across 4 domains.")

# ---------------------------------------------------------------------------
# Entry point (fallback — prefer main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()

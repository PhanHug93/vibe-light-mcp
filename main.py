#!/usr/bin/env python3
"""Entry point for TechStack Local MCP Server.

This thin wrapper ensures the MCP client config (which points to this file)
continues to work after the source tree restructure.

Usage (by MCP clients):
    python main.py

The actual server implementation lives in ``src/server.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

# ── Ensure stdout is NEVER used for non-MCP output ──────────────────
# MCP stdio transport uses stdout exclusively for JSON-RPC.
# Any stray print() or library output to stdout will corrupt the protocol.
# Redirect stderr for logging (logging.basicConfig already uses stderr).
import os

# Ensure the project root is on sys.path so that ``src.*`` imports work
# regardless of how the MCP client launches this script.
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.server import mcp, __version__  # noqa: E402

if __name__ == "__main__":
    # Startup diagnostic (goes to stderr, never stdout)
    print(
        f"[MCP] TechStackLocalMCP v{__version__} starting "
        f"(pid={os.getpid()}, transport=stdio)",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")

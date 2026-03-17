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

# Ensure the project root is on sys.path so that ``src.*`` imports work
# regardless of how the MCP client launches this script.
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.server import mcp  # noqa: E402

if __name__ == "__main__":
    mcp.run()

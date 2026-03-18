#!/usr/bin/env python3
"""Entry point for TechStack Local MCP Server.

Supports 3 transport protocols:
    stdio             — default, for Antigravity/Claude (pipe-based)
    sse               — HTTP + Server-Sent Events (streaming)
    streamable-http   — Newer MCP spec, single /mcp endpoint (streaming)

Usage::

    # Default: stdio (backward compatible)
    python main.py

    # SSE server on port 8000
    python main.py --transport sse
    python main.py --transport sse --port 9000

    # Streamable HTTP
    python main.py --transport streamable-http --port 8000

    # Environment variables (alternative to CLI)
    MCP_TRANSPORT=sse MCP_PORT=9000 python main.py

The actual server implementation lives in ``src/server.py``.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so that ``src.*`` imports work
# regardless of how the MCP client launches this script.
_project_root = str(Path(__file__).resolve().parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from src.config import MCP_TRANSPORT, MCP_HOST, MCP_PORT  # noqa: E402


def _parse_args() -> argparse.Namespace:
    """Parse CLI arguments with env-var fallbacks from config."""
    parser = argparse.ArgumentParser(
        description="TechStack Local MCP Server",
    )
    parser.add_argument(
        "--transport", "-t",
        choices=["stdio", "sse", "streamable-http"],
        default=MCP_TRANSPORT,
        help="Transport protocol (default: %(default)s, env: MCP_TRANSPORT)",
    )
    parser.add_argument(
        "--host",
        default=MCP_HOST,
        help="Bind address for HTTP transports (default: %(default)s, env: MCP_HOST)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=MCP_PORT,
        help="Listen port for HTTP transports (default: %(default)s, env: MCP_PORT)",
    )
    return parser.parse_args()


def main() -> None:
    """Boot the MCP server with the selected transport."""
    args = _parse_args()

    # Import server (registers all tools via decorators)
    from src.server import mcp, __version__  # noqa: E402

    # Configure host/port for HTTP transports
    mcp.settings.host = args.host
    mcp.settings.port = args.port

    # Startup diagnostic (stderr only — never pollute stdout/stdio)
    transport_info = f"transport={args.transport}"
    if args.transport != "stdio":
        transport_info += f", {args.host}:{args.port}"

    print(
        f"[MCP] TechStackLocalMCP v{__version__} starting "
        f"(pid={os.getpid()}, {transport_info})",
        file=sys.stderr,
    )

    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()

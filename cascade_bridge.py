#!/usr/bin/env python3
"""Cascade Bridge — stdio ↔ SSE/HTTP proxy for MCP.

This script acts as a thin proxy between an MCP client that expects ``stdio``
(like Windsurf Cascade on Android Studio) and the TechStack MCP Server
running as an SSE or Streamable HTTP server.

Architecture::

    Cascade (stdio) ──► cascade_bridge.py ──► MCP SSE Server (HTTP)
        stdin/stdout         proxy              127.0.0.1:8000

Usage in Cascade/Windsurf config::

    {
      "mcpServers": {
        "tech-stack-expert": {
          "command": "/path/to/.venv/bin/python",
          "args": ["/path/to/cascade_bridge.py"]
        }
      }
    }

Environment variables::

    MCP_BRIDGE_URL   — Server URL (default: http://127.0.0.1:8000)
    MCP_BRIDGE_MODE  — "sse" or "http" (default: "sse")
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Logging — always stderr (stdout is reserved for MCP stdio protocol)
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | cascade_bridge | %(levelname)-7s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("cascade_bridge")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

_SERVER_URL: str = os.getenv("MCP_BRIDGE_URL", "http://127.0.0.1:8000")
_BRIDGE_MODE: str = os.getenv("MCP_BRIDGE_MODE", "sse")  # "sse" | "http"
_REQUEST_TIMEOUT: int = 60  # seconds per tool call
_CONNECT_TIMEOUT: int = 5   # seconds for initial connection


# ---------------------------------------------------------------------------
# SSE Bridge — connects to /sse, sends via /messages/
# ---------------------------------------------------------------------------

async def _run_sse_bridge() -> None:
    """Bridge stdio ↔ SSE transport.

    1. Open persistent SSE connection to ``/sse``
    2. Read JSON-RPC messages from stdin
    3. POST each message to ``/messages/``
    4. Read SSE events and write them to stdout
    """
    try:
        import httpx
    except ImportError:
        logger.error("httpx is required: pip install httpx")
        sys.exit(1)

    sse_url = f"{_SERVER_URL}/sse"
    messages_url: str | None = None

    logger.info("Connecting to SSE at %s ...", sse_url)

    async with httpx.AsyncClient(timeout=httpx.Timeout(_REQUEST_TIMEOUT)) as client:
        # --- SSE connection (background task reads events) ---
        response_queue: asyncio.Queue[str] = asyncio.Queue()

        async def _read_sse() -> None:
            """Read SSE events and push to queue."""
            nonlocal messages_url
            try:
                async with client.stream("GET", sse_url) as resp:
                    resp.raise_for_status()
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n\n" in buffer:
                            event_text, buffer = buffer.split("\n\n", 1)
                            for line in event_text.split("\n"):
                                if line.startswith("event: endpoint"):
                                    continue
                                if line.startswith("data: "):
                                    data = line[6:]
                                    # First event from SSE is the messages endpoint
                                    if messages_url is None and data.startswith("/"):
                                        # Resolve relative URL
                                        messages_url = f"{_SERVER_URL}{data}"
                                        logger.info("Messages endpoint: %s", messages_url)
                                    else:
                                        await response_queue.put(data)
            except httpx.HTTPError as exc:
                logger.error("SSE connection error: %s", exc)
            except Exception as exc:
                logger.error("SSE reader error: %s", exc)

        # Start SSE reader in background
        sse_task = asyncio.create_task(_read_sse())

        # Wait for messages endpoint to be discovered
        for _ in range(50):  # 5s max
            if messages_url is not None:
                break
            await asyncio.sleep(0.1)

        if messages_url is None:
            logger.error("Timeout: SSE did not provide messages endpoint")
            sys.exit(1)

        logger.info("Bridge ready (pid=%d, mode=sse)", os.getpid())

        # --- Stdin reader → POST to messages endpoint ---
        loop = asyncio.get_event_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        async def _read_stdin() -> None:
            """Read JSON-RPC from stdin and POST to server."""
            while True:
                line = await reader.readline()
                if not line:
                    break  # EOF

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                # Validate JSON
                try:
                    json.loads(line_str)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from stdin: %s", line_str[:100])
                    continue

                # POST to MCP server
                try:
                    resp = await client.post(
                        messages_url,
                        content=line_str,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code not in (200, 202):
                        logger.warning(
                            "Server returned %d: %s",
                            resp.status_code,
                            resp.text[:200],
                        )
                except httpx.HTTPError as exc:
                    error_response = json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": f"Bridge connection error: {exc}",
                        },
                    })
                    sys.stdout.write(error_response + "\n")
                    sys.stdout.flush()

        stdin_task = asyncio.create_task(_read_stdin())

        # --- Response writer: queue → stdout ---
        async def _write_responses() -> None:
            """Write SSE events to stdout for the MCP client."""
            while True:
                data = await response_queue.get()
                sys.stdout.write(data + "\n")
                sys.stdout.flush()

        writer_task = asyncio.create_task(_write_responses())

        # Wait for stdin EOF or SSE disconnect
        done, pending = await asyncio.wait(
            [sse_task, stdin_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()


# ---------------------------------------------------------------------------
# Streamable HTTP Bridge — simpler, single /mcp endpoint
# ---------------------------------------------------------------------------

async def _run_http_bridge() -> None:
    """Bridge stdio ↔ Streamable HTTP transport.

    Each stdin JSON-RPC message → POST to ``/mcp`` → stream response to stdout.
    Simpler than SSE: no persistent connection needed.
    """
    try:
        import httpx
    except ImportError:
        logger.error("httpx is required: pip install httpx")
        sys.exit(1)

    mcp_url = f"{_SERVER_URL}/mcp"
    logger.info("Bridge ready (pid=%d, mode=http, url=%s)", os.getpid(), mcp_url)

    # Read from stdin line by line
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    async with httpx.AsyncClient(timeout=httpx.Timeout(_REQUEST_TIMEOUT)) as client:
        while True:
            line = await reader.readline()
            if not line:
                break  # EOF

            line_str = line.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                json.loads(line_str)  # validate
            except json.JSONDecodeError:
                logger.warning("Invalid JSON: %s", line_str[:100])
                continue

            try:
                async with client.stream(
                    "POST",
                    mcp_url,
                    content=line_str,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                ) as resp:
                    async for chunk in resp.aiter_text():
                        # Write each streamed chunk to stdout
                        for line_part in chunk.split("\n"):
                            stripped = line_part.strip()
                            if stripped and not stripped.startswith("event:"):
                                # Extract data from SSE-style events
                                if stripped.startswith("data: "):
                                    stripped = stripped[6:]
                                if stripped:
                                    sys.stdout.write(stripped + "\n")
                                    sys.stdout.flush()
            except httpx.HTTPError as exc:
                error_response = json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32000,
                        "message": f"Bridge error: {exc}",
                    },
                })
                sys.stdout.write(error_response + "\n")
                sys.stdout.flush()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the bridge in the configured mode."""
    # Ensure project root on sys.path
    project_root = str(Path(__file__).resolve().parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    logger.info(
        "Starting Cascade bridge (mode=%s, server=%s)",
        _BRIDGE_MODE,
        _SERVER_URL,
    )

    if _BRIDGE_MODE == "sse":
        asyncio.run(_run_sse_bridge())
    elif _BRIDGE_MODE in ("http", "streamable-http"):
        asyncio.run(_run_http_bridge())
    else:
        logger.error("Unknown bridge mode: %s (use 'sse' or 'http')", _BRIDGE_MODE)
        sys.exit(1)


if __name__ == "__main__":
    main()

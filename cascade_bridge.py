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

v1.0.14 — Replaced httpx with aiohttp to fix SSE buffering/hang bug.
  httpx's aiter_text() buffers internally before yielding, breaking real-time
  SSE delivery.  aiohttp's response.content.readline() delivers each line
  the instant the server flushes it — true streaming with zero buffering delay.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import sys
from pathlib import Path

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
_CONNECT_TIMEOUT: int = 10  # seconds for initial SSE connection
_RECONNECT_BASE: float = 1.0  # initial reconnect delay (seconds)
_RECONNECT_MAX: float = 30.0  # max reconnect delay (seconds)


# ---------------------------------------------------------------------------
# SSE Bridge — connects to /sse, sends via /messages/
# ---------------------------------------------------------------------------


async def _run_sse_bridge() -> None:
    """Bridge stdio ↔ SSE transport using **aiohttp**.

    Key design decisions:
    - ``response.content.readline()`` reads exactly one ``\\n``-terminated
      line from the TCP stream.  Unlike httpx's ``aiter_text()``, aiohttp
      does NOT internally buffer multiple chunks — each line is yielded as
      soon as the server flushes it.
    - A proper SSE state machine accumulates ``event:`` and ``data:`` fields
      and dispatches on blank lines (``\\n\\n``).
    - POST requests use a separate ``ClientSession`` with a finite timeout.
    - stdin is read via ``run_in_executor`` for Windows ProactorEventLoop
      compatibility.
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp is required: pip install aiohttp>=3.9.0")
        sys.exit(1)

    sse_url = f"{_SERVER_URL}/sse"
    messages_url: str | None = None

    logger.info("Connecting to SSE at %s ...", sse_url)

    # ── Shared state ────────────────────────────────────────────────────
    response_queue: asyncio.Queue[str] = asyncio.Queue()
    endpoint_ready = asyncio.Event()
    shutdown_event = asyncio.Event()

    # ── SSE reader ──────────────────────────────────────────────────────

    async def _read_sse(session: aiohttp.ClientSession) -> None:
        """Read SSE events line-by-line with zero buffering delay."""
        nonlocal messages_url

        sse_timeout = aiohttp.ClientTimeout(
            total=None,  # SSE stream lives forever
            connect=_CONNECT_TIMEOUT,
            sock_read=None,  # no read timeout on persistent stream
        )

        reconnect_delay = _RECONNECT_BASE

        while not shutdown_event.is_set():
            try:
                async with session.get(sse_url, timeout=sse_timeout) as resp:
                    if resp.status != 200:
                        logger.error("SSE connection refused: HTTP %d", resp.status)
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX)
                        continue

                    # Connection succeeded — reset reconnect delay
                    reconnect_delay = _RECONNECT_BASE

                    # SSE state machine
                    event_type: str = ""
                    data_lines: list[str] = []

                    # readline() returns one \n-terminated line from the
                    # raw TCP chunked stream — NO internal buffering.
                    while True:
                        raw_line = await resp.content.readline()
                        if not raw_line:
                            # Server closed connection
                            logger.warning("SSE stream closed by server")
                            break

                        line = raw_line.decode("utf-8", errors="replace")

                        # Strip trailing \n or \r\n
                        line = line.rstrip("\r\n")

                        # Blank line → dispatch accumulated event
                        if not line:
                            if data_lines:
                                data = "\n".join(data_lines)

                                # First event: server sends the messages
                                # endpoint path (e.g. "/messages/?session=...")
                                if (
                                    messages_url is None
                                    and event_type == "endpoint"
                                    and data.startswith("/")
                                ):
                                    messages_url = f"{_SERVER_URL}{data}"
                                    logger.info("Messages endpoint: %s", messages_url)
                                    endpoint_ready.set()
                                elif event_type == "message" or (
                                    event_type == "" and messages_url is not None
                                ):
                                    # Regular MCP JSON-RPC event → stdout
                                    await response_queue.put(data)

                            # Reset for next event
                            event_type = ""
                            data_lines = []
                            continue

                        # SSE field parsing
                        if line.startswith("event:"):
                            event_type = line[6:].strip()
                        elif line.startswith("data:"):
                            data_lines.append(line[5:].strip())
                        elif line.startswith("id:"):
                            pass  # SSE spec says to track, but MCP doesn't use it
                        elif line.startswith("retry:"):
                            pass  # Could update reconnect delay
                        elif line.startswith(":"):
                            pass  # SSE comment — heartbeat / keep-alive

            except aiohttp.ClientError as exc:
                logger.error("SSE connection error: %s", exc)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("SSE reader unexpected error: %s", exc)

            # ── Reset session state for reconnect ───────────────────
            # Server will create a NEW session with a different endpoint
            # URL.  We MUST accept it, so clear the old one.
            messages_url = None
            endpoint_ready.clear()

            # Drain stale responses from the dead session (#7)
            drained = 0
            while not response_queue.empty():
                try:
                    response_queue.get_nowait()
                    drained += 1
                except asyncio.QueueEmpty:
                    break
            if drained:
                logger.info("Drained %d stale events from previous session", drained)

            logger.info("Session reset — will acquire new endpoint on reconnect")

            # Reconnect with exponential backoff
            if not shutdown_event.is_set():
                logger.info("Reconnecting to SSE in %.1fs ...", reconnect_delay)
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, _RECONNECT_MAX)

        # SSE reader exited the while loop — signal others to stop (#6)
        shutdown_event.set()

    # ── POST session (separate, with finite timeout) ────────────────────

    async def _read_stdin(post_session: aiohttp.ClientSession) -> None:
        """Read JSON-RPC from stdin and POST to the MCP server."""
        loop = asyncio.get_running_loop()

        while not shutdown_event.is_set():
            # Read stdin in thread pool — works on all platforms
            line_bytes = await loop.run_in_executor(
                None,
                sys.stdin.buffer.readline,
            )
            if not line_bytes:
                logger.info("stdin EOF — shutting down")
                shutdown_event.set()
                break

            line_str = line_bytes.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            # Validate JSON
            try:
                json.loads(line_str)
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from stdin: %s", line_str[:100])
                continue

            # Snapshot to avoid TOCTOU race with _read_sse (#1)
            url = messages_url
            if url is None:
                logger.info("Waiting for endpoint (reconnecting)...")
                try:
                    await asyncio.wait_for(
                        endpoint_ready.wait(), timeout=_CONNECT_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Endpoint not available, dropping: %s",
                        line_str[:80],
                    )
                    continue
                # Re-read after wait — _read_sse may have set it
                url = messages_url
                if url is None:
                    logger.warning("Endpoint still None after wait, dropping")
                    continue

            # POST to MCP server
            try:
                async with post_session.post(
                    url,
                    data=line_str,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status not in (200, 202):
                        body = await resp.text()
                        logger.warning(
                            "Server returned %d: %s",
                            resp.status,
                            body[:200],
                        )
            except aiohttp.ClientError as exc:
                error_response = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": f"Bridge connection error: {exc}",
                        },
                    }
                )
                sys.stdout.write(error_response + "\n")
                sys.stdout.flush()

    # ── Response writer: queue → stdout ─────────────────────────────────

    async def _write_responses() -> None:
        """Drain the queue and write to stdout immediately."""
        while not shutdown_event.is_set():
            try:
                data = await asyncio.wait_for(response_queue.get(), timeout=1.0)
                sys.stdout.write(data + "\n")
                sys.stdout.flush()
            except asyncio.TimeoutError:
                continue  # check shutdown flag
            except asyncio.CancelledError:
                return

    # ── Orchestrator ────────────────────────────────────────────────────

    import aiohttp

    async with (
        aiohttp.ClientSession() as sse_session,
        aiohttp.ClientSession() as post_session,
    ):
        sse_task = asyncio.create_task(_read_sse(sse_session))

        # Wait for the messages endpoint to be discovered
        try:
            await asyncio.wait_for(endpoint_ready.wait(), timeout=_CONNECT_TIMEOUT)
        except asyncio.TimeoutError:
            logger.error(
                "Timeout: SSE did not provide messages endpoint within %ds",
                _CONNECT_TIMEOUT,
            )
            sse_task.cancel()
            sys.exit(1)

        logger.info("Bridge ready (pid=%d, mode=sse)", os.getpid())

        stdin_task = asyncio.create_task(_read_stdin(post_session))
        writer_task = asyncio.create_task(_write_responses())

        # Wait for any task to finish (usually stdin EOF)
        done, pending = await asyncio.wait(
            [sse_task, stdin_task, writer_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        shutdown_event.set()
        for task in pending:
            task.cancel()
        # Suppress CancelledError from pending tasks
        await asyncio.gather(*pending, return_exceptions=True)

    logger.info("Bridge shutdown complete")


# ---------------------------------------------------------------------------
# Streamable HTTP Bridge — simpler, single /mcp endpoint
# ---------------------------------------------------------------------------


async def _run_http_bridge() -> None:
    """Bridge stdio ↔ Streamable HTTP transport.

    Each stdin JSON-RPC message → POST to ``/mcp`` → stream response to stdout.
    Simpler than SSE: no persistent connection needed.
    Uses aiohttp for consistent streaming behavior.
    """
    try:
        import aiohttp
    except ImportError:
        logger.error("aiohttp is required: pip install aiohttp>=3.9.0")
        sys.exit(1)

    mcp_url = f"{_SERVER_URL}/mcp"
    logger.info("Bridge ready (pid=%d, mode=http, url=%s)", os.getpid(), mcp_url)

    loop = asyncio.get_event_loop()

    async with aiohttp.ClientSession() as session:
        while True:
            # Read stdin in thread pool — works on all platforms
            line_bytes = await loop.run_in_executor(
                None,
                sys.stdin.buffer.readline,
            )
            if not line_bytes:
                break  # EOF

            line_str = line_bytes.decode("utf-8", errors="replace").strip()
            if not line_str:
                continue

            try:
                json.loads(line_str)  # validate
            except json.JSONDecodeError:
                logger.warning("Invalid JSON: %s", line_str[:100])
                continue

            try:
                async with session.post(
                    mcp_url,
                    data=line_str,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    timeout=aiohttp.ClientTimeout(total=_REQUEST_TIMEOUT),
                ) as resp:
                    # Stream the response line by line
                    while True:
                        raw_line = await resp.content.readline()
                        if not raw_line:
                            break
                        line = raw_line.decode("utf-8", errors="replace").strip()
                        if not line or line.startswith("event:"):
                            continue
                        if line.startswith("data:"):
                            line = line[5:].strip()
                        if line:
                            sys.stdout.write(line + "\n")
                            sys.stdout.flush()

            except aiohttp.ClientError as exc:
                error_response = json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32000,
                            "message": f"Bridge error: {exc}",
                        },
                    }
                )
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

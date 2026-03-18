#!/usr/bin/env python3
"""Test client for MCP SSE / Streamable HTTP endpoints.

Verifies the MCP server is reachable and tools respond correctly.

Usage::

    # Start server first
    python main.py --transport sse --port 8000

    # Then run tests
    python scripts/test_sse_client.py
    python scripts/test_sse_client.py --mode http
    python scripts/test_sse_client.py --url http://127.0.0.1:9000

Equivalent curl commands::

    # SSE: list tools
    curl -N http://127.0.0.1:8000/sse

    # Streamable HTTP: call server_health
    curl -X POST http://127.0.0.1:8000/mcp \\
      -H 'Content-Type: application/json' \\
      -H 'Accept: application/json, text/event-stream' \\
      -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}'
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys


async def test_sse(url: str) -> bool:
    """Test SSE endpoint: connect, read first event (endpoint discovery)."""
    try:
        import httpx
    except ImportError:
        print("❌ httpx required: pip install httpx", file=sys.stderr)
        return False

    sse_url = f"{url}/sse"
    print(f"🔍 Testing SSE at {sse_url} ...")

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            async with client.stream("GET", sse_url) as resp:
                if resp.status_code != 200:
                    print(f"❌ SSE returned {resp.status_code}")
                    return False

                # Read first event (should be endpoint)
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    if "\n\n" in buffer:
                        event_text = buffer.split("\n\n")[0]
                        print(f"✅ SSE connected! First event:\n   {event_text}")
                        return True

    except httpx.ConnectError:
        print(f"❌ Cannot connect to {sse_url} — is the server running?")
    except Exception as exc:
        print(f"❌ Error: {exc}")

    return False


async def test_http(url: str) -> bool:
    """Test Streamable HTTP endpoint with MCP initialize."""
    try:
        import httpx
    except ImportError:
        print("❌ httpx required: pip install httpx", file=sys.stderr)
        return False

    mcp_url = f"{url}/mcp"
    print(f"🔍 Testing Streamable HTTP at {mcp_url} ...")

    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test_client", "version": "1.0"},
        },
    }

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
            resp = await client.post(
                mcp_url,
                json=init_request,
                headers={"Accept": "application/json, text/event-stream"},
            )
            print(f"   Status: {resp.status_code}")
            print(f"   Content-Type: {resp.headers.get('content-type', 'N/A')}")

            if resp.status_code in (200, 202):
                body = resp.text[:500]
                print(f"✅ Server responded:\n   {body}")
                return True
            else:
                print(f"❌ Unexpected status: {resp.status_code}")
                print(f"   Body: {resp.text[:300]}")
                return False

    except httpx.ConnectError:
        print(f"❌ Cannot connect to {mcp_url} — is the server running?")
    except Exception as exc:
        print(f"❌ Error: {exc}")

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Test MCP HTTP endpoints")
    parser.add_argument(
        "--url", default="http://127.0.0.1:8000",
        help="Server URL (default: %(default)s)",
    )
    parser.add_argument(
        "--mode", choices=["sse", "http", "both"], default="both",
        help="Which transport to test (default: %(default)s)",
    )
    args = parser.parse_args()

    results: dict[str, bool] = {}

    if args.mode in ("sse", "both"):
        results["SSE"] = asyncio.run(test_sse(args.url))

    if args.mode in ("http", "both"):
        results["HTTP"] = asyncio.run(test_http(args.url))

    print()
    print("─" * 40)
    for name, ok in results.items():
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {name}: {status}")

    if not all(results.values()):
        print("\n💡 Start the server first:")
        print(f"   python main.py --transport sse --port {args.url.split(':')[-1]}")
        sys.exit(1)


if __name__ == "__main__":
    main()

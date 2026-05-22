"""Tests for the get_skills MCP tool wrapper."""

from __future__ import annotations

import asyncio
import json

from mcp.server.fastmcp import FastMCP

from src.tools.skills import register_skill_tools


def test_get_skills_tool_returns_json_payload() -> None:
    mcp = FastMCP("test-skills")
    register_skill_tools(mcp)

    content, structured = asyncio.run(
        mcp.call_tool(
            "get_skills",
            {
                "requested_skills": ["android"],
                "languages": ["kotlin"],
                "mode": "auto",
                "max_tokens": 1200,
            },
        )
    )
    payload = json.loads(content[0].text)

    assert structured["result"] == content[0].text
    assert payload["status"] == "success"
    assert payload["skills"][0]["id"] == "android-kotlin"


def test_server_registers_get_skills_tool() -> None:
    from src.server import mcp

    assert "get_skills" in mcp._tool_manager._tools

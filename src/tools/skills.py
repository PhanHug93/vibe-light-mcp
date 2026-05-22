"""Skill-related MCP tools for local audited skill delivery."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from src.engine.skills import get_skill_bundle
from src.utils.usage_tracker import record_tool_call


def register_skill_tools(mcp: FastMCP) -> None:
    """Register local skill retrieval tools onto the FastMCP instance."""

    @mcp.tool()
    async def get_skills(
        requested_skills: list[str],
        languages: list[str] | None = None,
        mode: str = "auto",
        active_hashes: list[str] | None = None,
        max_tokens: int = 1800,
    ) -> str:
        """Get audited local skills for an agent to use in the next LLM call.

        Call this tool before coding/reviewing when local skill policy is needed.
        It never fetches dynamic online skills; unmatched facets are reported
        explicitly so the agent does not rely on unaudited remote instructions.

        Args:
            requested_skills: Platform/facet IDs, e.g. ["android"].
            languages: Optional language constraints, e.g. ["kotlin"].
            mode: Delivery mode: auto, digest, hash_only, delta, or full.
            active_hashes: Skill hashes already present in the conversation.
            max_tokens: Maximum MCP-derived skill context budget.

        Returns:
            JSON with matched local skill payloads and unmatched terms.
        """
        result = get_skill_bundle(
            requested_skills=requested_skills,
            languages=languages,
            mode=mode,
            active_hashes=active_hashes,
            max_tokens=max_tokens,
        )
        matched_ids = ",".join(skill["id"] for skill in result.get("skills", []))
        record_tool_call(
            "get_skills",
            stack=matched_ids or "none",
            query=",".join(requested_skills or []),
            metadata={
                "languages": languages or [],
                "mode": mode,
                "status": result.get("status"),
            },
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

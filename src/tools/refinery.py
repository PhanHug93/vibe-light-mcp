"""Refinery-related MCP tools - compact payload preparation for LLM calls."""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP

from src.engine.refinery import prepare_payload_bundle
from src.tools.helpers import (
    WORKSPACE_ERROR_MSG,
    make_session_namespace,
    make_workspace_id,
    validate_memory_scope,
    validate_session_scope_inputs,
    validate_stack_name,
)
from src.utils.usage_tracker import record_tool_call


def register_refinery_tools(mcp: FastMCP) -> None:
    """Register payload-refinery tools onto the FastMCP instance."""

    @mcp.tool()
    async def prepare_llm_payload(
        user_input: str,
        workspace_path: str,
        tech_stack: str = "",
        max_context_tokens: int = 3500,
        memory_scope: str = "workspace",
        agent_id: str = "",
        session_id: str = "",
    ) -> str:
        """Prepare a compact, structured payload for the next LLM call.

        Call this tool when user asks to:
        - reduce MCP context before the next agent/LLM request
        - create a gateway payload instead of passing raw memory/tool output
        - prepare only the highest-signal context for the current task

        The flow is independent:
        - normalize task intent
        - inspect workspace and tech-stack knowledge
        - retrieve top memory evidence from L1/L2
        - enforce a fixed context budget

        Args:
            user_input: The current user request or task description.
            workspace_path: Absolute path to the active project root.
            tech_stack: Optional explicit stack override.
            max_context_tokens: Budget reserved for MCP-derived context.
            memory_scope: Which memory view to query (`workspace`, `session`, `global`).
            agent_id: REQUIRED when memory_scope="session" for isolation.
            session_id: Optional finer-grained conversation discriminator.

        Returns:
            JSON with structured context_blocks plus a compiled_context string.
        """
        try:
            workspace_id = make_workspace_id(workspace_path)
        except ValueError:
            return json.dumps(
                {"status": "error", "message": WORKSPACE_ERROR_MSG},
                ensure_ascii=False,
            )

        stack = tech_stack.strip()
        if stack:
            stack_err = validate_stack_name(stack)
            if stack_err:
                return json.dumps(
                    {"status": "error", "message": stack_err},
                    ensure_ascii=False,
                )
        else:
            stack = ""
        scope = memory_scope.strip().lower()
        scope_err = validate_memory_scope(scope)
        if scope_err:
            return json.dumps(
                {"status": "error", "message": scope_err},
                ensure_ascii=False,
            )
        session_namespace = None
        if scope == "session":
            session_input_err = validate_session_scope_inputs(agent_id, session_id)
            if session_input_err:
                return json.dumps(
                    {"status": "error", "message": session_input_err},
                    ensure_ascii=False,
                )
            try:
                session_namespace = make_session_namespace(
                    workspace_path,
                    agent_id=agent_id,
                    session_id=session_id,
                )
            except ValueError as exc:
                return json.dumps(
                    {"status": "error", "message": str(exc)},
                    ensure_ascii=False,
                )

        result = await prepare_payload_bundle(
            user_input=user_input,
            workspace_path=workspace_path,
            workspace_id=workspace_id,
            tech_stack=stack or None,
            max_context_tokens=max_context_tokens,
            memory_scope=scope,
            agent_id=agent_id.strip(),
            session_id=session_id.strip(),
            session_namespace=session_namespace,
        )

        detected_stack = stack or None
        try:
            payload = json.loads(result)
            detected_stack = payload.get("workspace", {}).get("tech_stack") or detected_stack
        except json.JSONDecodeError:
            pass

        record_tool_call(
            "prepare_llm_payload",
            stack=detected_stack,
            query=user_input[:100],
            metadata={
                "max_context_tokens": max_context_tokens,
                "memory_scope": scope,
                "agent_id": agent_id.strip(),
                "session_id": session_id.strip(),
            },
        )
        return result

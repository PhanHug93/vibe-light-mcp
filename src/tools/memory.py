"""Memory-related MCP tools — store, search, recall, cleanup, stats.

Extracted from ``server.py`` for SRP compliance.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time as _time

from mcp.server.fastmcp import FastMCP

from src.engine.context import (
    compress_and_store,
    query_memory,
    quick_recall,
    cleanup_l1,
    get_memory_stats,
)
from src.tools.helpers import make_workspace_id, WORKSPACE_ERROR_MSG
from src.utils.usage_tracker import record_tool_call

# Rate limiter state for auto_recall
_recall_cache: dict[str, tuple[float, str]] = {}
_RECALL_COOLDOWN: float = 3.0
_RECALL_CACHE_SIZE: int = 20
_recall_lock = asyncio.Lock()


def register_memory_tools(mcp: FastMCP) -> None:
    """Register memory-related tools onto the FastMCP instance."""

    @mcp.tool()
    async def store_working_context(
        text_data: str,
        metadata_source: str,
        workspace_path: str,
        tech_stack: str = "general",
    ) -> str:
        """Store working context into L1 (per-workspace short-term memory).

        Call this tool when user asks to:
        - Save, store, or remember code, logs, or error traces
        - Keep context about current work for later retrieval
        - Cache file contents or debugging output

        Use for: code files, logs, error traces, draft designs.
        Auto-cleaned after 3 days.

        Args:
            text_data: The text content to store.
            metadata_source: Label describing the origin (file path, URL, etc.).
            workspace_path: ⚠️ REQUIRED. The absolute path of the project root
                directory (e.g. /Users/admin/projects/my-android-app). Infer this
                from the file paths the user is currently editing. DO NOT omit.
            tech_stack: Tech stack tag (e.g. android_kotlin, flutter_dart).

        Returns:
            JSON string reporting storage status.
        """
        try:
            ws_id = make_workspace_id(workspace_path)
        except ValueError:
            return json.dumps(
                {"status": "error", "message": WORKSPACE_ERROR_MSG},
                ensure_ascii=False,
            )
        result = await compress_and_store(
            text_data, metadata_source, "L1", ws_id, tech_stack
        )
        record_tool_call("compress_and_store_context", query=metadata_source)
        return result

    @mcp.tool()
    async def store_knowledge(
        text_data: str,
        metadata_source: str,
        tech_stack: str = "general",
    ) -> str:
        """Store knowledge into L2 (global long-term brain).

        Call this tool when user asks to:
        - Save a rule, best practice, or lesson learned permanently
        - Store a solved bug fix or boilerplate config for reuse
        - Add knowledge that should be available across all projects

        Permanent storage, shared across all workspaces.

        Args:
            text_data: The knowledge content to store.
            metadata_source: Label describing the origin.
            tech_stack: Tech stack tag for filtering.

        Returns:
            JSON string reporting storage status.
        """
        return await compress_and_store(
            text_data, metadata_source, "L2", "global", tech_stack
        )

    @mcp.tool()
    async def search_memory(
        query: str,
        workspace_path: str,
        n_results: int = 5,
        tech_stack: str = "",
    ) -> str:
        """Federated search across L1 (local) and L2 (global) memory.

        Call this tool when user asks to:
        - Search, find, or recall stored context or knowledge
        - Look up previous code, logs, errors, or best practices
        - Query the memory / knowledge base for relevant information

        Queries both tiers, merges results, re-ranks by similarity distance.
        Results are tagged [L1_LOCAL] or [L2_GLOBAL] for context awareness.

        Args:
            query: Natural-language query to search for.
            workspace_path: ⚠️ REQUIRED. The absolute path of the project root
                directory (e.g. /Users/admin/projects/my-android-app). Infer this
                from the file paths the user is currently editing. DO NOT omit.
            n_results: Total results to return after merge (default 5).
            tech_stack: If provided, only search within this tech stack.

        Returns:
            JSON with merged, re-ranked results from both memory tiers.
        """
        try:
            ws_id = make_workspace_id(workspace_path)
        except ValueError:
            return json.dumps(
                {"status": "error", "message": WORKSPACE_ERROR_MSG},
                ensure_ascii=False,
            )
        result = await query_memory(query, ws_id, tech_stack or None, n_results)
        record_tool_call("query_local_memory", query=query)
        return result

    @mcp.tool()
    async def auto_recall(
        user_message: str,
        workspace_path: str,
        tech_stack: str = "",
        n_results: int = 3,
    ) -> str:
        """⚡ Auto-retrieve relevant context from memory for the current conversation.

        IMPORTANT: Call this at the START of every conversation to recall
        previous context and avoid losing information from past sessions.
        Also call when the conversation is getting long (>10 turns) to
        refresh your memory.

        This tool is:
        - Rate-limited (max 1 query per 3s, duplicates return cached results)
        - Fail-safe (always returns valid JSON, never blocks)
        - Fast (5s timeout, compact output ≤3000 chars)

        Args:
            user_message: The user's current message to find relevant context for.
            workspace_path: ⚠️ REQUIRED. The absolute path of the project root
                directory (e.g. /Users/admin/projects/my-android-app). Infer this
                from the file paths the user is currently editing. DO NOT omit.
            tech_stack: Filter results by tech stack (optional).
            n_results: Max context chunks to return (default 3, max 5).

        Returns:
            JSON with status and recalled context (if any).
        """
        try:
            ws_id = make_workspace_id(workspace_path)
        except ValueError:
            return json.dumps(
                {"status": "error", "message": WORKSPACE_ERROR_MSG},
                ensure_ascii=False,
            )
        n_results = min(n_results, 5)

        # Rate limiter + Dedup (thread-safe)
        query_hash = hashlib.md5(
            f"{user_message}:{ws_id}:{tech_stack}".encode(),
        ).hexdigest()[:12]  # noqa: S324
        now = _time.time()

        async with _recall_lock:
            if query_hash in _recall_cache:
                cached_time, cached_result = _recall_cache[query_hash]
                if now - cached_time < _RECALL_COOLDOWN:
                    return json.dumps(
                        {
                            "status": "cached",
                            "message": "Using cached recall (rate-limited).",
                            "context": cached_result,
                        },
                        ensure_ascii=False,
                    )

            # Prune old cache entries
            if len(_recall_cache) > _RECALL_CACHE_SIZE:
                oldest_keys = sorted(_recall_cache, key=lambda k: _recall_cache[k][0])
                for k in oldest_keys[: len(oldest_keys) // 2]:
                    del _recall_cache[k]

        # Recall
        try:
            context = await quick_recall(
                query=user_message,
                workspace_id=ws_id,
                tech_stack=tech_stack or None,
                n_results=n_results,
            )
        except Exception:  # noqa: BLE001
            context = ""

        async with _recall_lock:
            _recall_cache[query_hash] = (now, context)
        record_tool_call("auto_recall", query=user_message[:100])

        if not context:
            return json.dumps(
                {
                    "status": "no_context",
                    "message": "No relevant context found in memory. This is normal for new topics.",
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "status": "success",
                "message": "Relevant context recalled from memory. Use this to inform your response.",
                "context": context,
            },
            ensure_ascii=False,
        )

    @mcp.tool()
    async def cleanup_workspace(
        workspace_path: str,
        days: int = 3,
    ) -> str:
        """Delete old L1 records to free resources.

        Call this tool when user asks to:
        - Clean up, clear, or free memory / context storage
        - Delete old or expired workspace data
        - Reset the local working memory

        Args:
            workspace_path: ⚠️ REQUIRED. The absolute path of the project root
                directory (e.g. /Users/admin/projects/my-android-app). Infer this
                from the file paths the user is currently editing. DO NOT omit.
            days: Records older than this will be deleted (default 3).

        Returns:
            JSON with deletion count and remaining records.
        """
        try:
            ws_id = make_workspace_id(workspace_path)
        except ValueError:
            return json.dumps(
                {"status": "error", "message": WORKSPACE_ERROR_MSG},
                ensure_ascii=False,
            )
        return await cleanup_l1(ws_id, days)

    @mcp.tool()
    async def memory_stats() -> str:
        """Get L1/L2 memory statistics: collection counts and chunk totals.

        Call this tool when user asks to:
        - Check memory usage, storage stats, or how much context is stored
        - View workspace or knowledge base statistics
        - See how many chunks or collections exist

        Returns:
            JSON with L1 workspace stats and L2 global chunk count.
        """
        return await get_memory_stats()

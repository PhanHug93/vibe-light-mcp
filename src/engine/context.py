"""Context Engine — Hybrid RAG (L1/L2 Memory) via ChromaDB HTTP.

Two-tier memory architecture:
  - **L1 (Local Working Memory)**: Per-workspace, short-term context
    (code files, logs, drafts). Auto-cleanup after 3 days.
  - **L2 (Global Knowledge Brain)**: Cross-workspace, permanent knowledge
    (rules, skills, solved bugs, boilerplate configs).

Architecture (after SOLID refactoring):
  - **ChromaManager** (``src.db.chroma_manager``) — connection pooling,
    health checks, auto-reconnect, thread pool isolation.
  - **Embedding** (``src.db.embedding``) — thread-safe embedding singleton.
  - **This module** — store, query, cleanup, recall logic only.

Usage::

    from src.engine.context import (
        compress_and_store, query_memory, quick_recall,
        cleanup_l1, get_memory_stats,
    )
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import typing
from datetime import datetime, timedelta, timezone

from src.config import (
    CHROMA_OP_TIMEOUT,
    L1_PREFIX,
    L2_COLLECTION,
    L1_TTL_DAYS,
    QUICK_RECALL_TIMEOUT,
    QUICK_RECALL_MAX_CHARS,
)
from src.db.chroma_manager import ChromaManager, get_manager
from src.db.embedding import get_embedding_fn, pre_warm_embedding  # noqa: F401 — re-exported
from src.utils.text_splitter import recursive_text_split

logger = logging.getLogger(__name__)

# Convenience aliases
_L1_PREFIX: str = L1_PREFIX
_L2_COLLECTION: str = L2_COLLECTION
_L1_TTL_DAYS: int = L1_TTL_DAYS
_CHROMA_OP_TIMEOUT: int = CHROMA_OP_TIMEOUT
_QUICK_RECALL_TIMEOUT: int = QUICK_RECALL_TIMEOUT
_QUICK_RECALL_MAX_CHARS: int = QUICK_RECALL_MAX_CHARS

# Singleton manager (lazy via get_manager())
_mgr: ChromaManager = None  # type: ignore[assignment]


def _get_mgr() -> ChromaManager:
    """Return the singleton manager (lazy init)."""
    global _mgr  # noqa: PLW0603
    if _mgr is None:
        _mgr = get_manager()
    return _mgr

# ---------------------------------------------------------------------------
# Sync Core Functions (all ChromaDB calls go through _mgr)
# ---------------------------------------------------------------------------


def _sync_store(
    text_data: str,
    metadata_source: str,
    tier: str = "L1",
    workspace_id: str = "default",
    tech_stack: str = "general",
) -> str:
    """Chunk and store text into L1 or L2 collection.

    Runs inside ``_mgr._executor`` — calls ChromaDB directly (no nested
    executor submissions).
    """
    mgr = _get_mgr()
    chunks = recursive_text_split(text_data)
    if not chunks:
        return json.dumps(
            {"status": "skipped", "message": "Input text is empty."},
            ensure_ascii=False,
        )

    try:
        if tier == "L2":
            collection = mgr.get_l2_direct()
            collection_name = _L2_COLLECTION
        else:
            collection = mgr.get_l1_direct(workspace_id)
            collection_name = f"{_L1_PREFIX}{workspace_id}"
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    batch_id: str = hashlib.md5(
        f"{metadata_source}:{tier}:{workspace_id}".encode()
    ).hexdigest()[:8]  # noqa: S324
    timestamp: str = datetime.now(timezone.utc).isoformat()

    # Content-hash IDs: same source + content → same ID → upsert overwrites.
    # Prevents DB bloat from repeated stores of the same file.
    ids = [
        hashlib.sha256(f"{metadata_source}:{chunk}".encode()).hexdigest()[:16] + f"_{i}"
        for i, chunk in enumerate(chunks)
    ]
    metadatas = [
        {
            "source": metadata_source,
            "tech_stack": tech_stack,
            "tier": tier,
            "workspace_id": workspace_id if tier == "L1" else "global",
            "timestamp": timestamp,
            "batch_id": batch_id,
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        for i in range(len(chunks))
    ]

    try:
        # upsert: same content+source → overwrite (no duplicates)
        collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)
    except Exception as exc:  # noqa: BLE001
        mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to store: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "success",
            "tier": tier,
            "collection": collection_name,
            "chunks_stored": len(chunks),
            "source": metadata_source,
            "tech_stack": tech_stack,
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# L1/L2 query helpers (for parallel execution)
# ---------------------------------------------------------------------------


def _query_single_tier(
    tier_label: str,
    collection_getter: typing.Callable,
    query: str,
    n_results: int,
    where_filter: dict | None,
) -> list[dict]:
    """Query a single tier (L1 or L2) and return formatted results."""
    mgr = _get_mgr()
    results: list[dict] = []
    try:
        col = collection_getter()
        count = col.count()
        if count > 0:
            n = min(n_results, count)
            raw = col.query(
                query_texts=[query],
                n_results=n,
                where=where_filter,
            )
            docs = raw["documents"][0] if raw["documents"] else []
            metas = raw["metadatas"][0] if raw["metadatas"] else []
            dists = raw["distances"][0] if raw.get("distances") else []
            for i, doc in enumerate(docs):
                results.append(
                    {
                        "tier": tier_label,
                        "document": doc,
                        "metadata": metas[i] if i < len(metas) else {},
                        "distance": dists[i] if i < len(dists) else 999.0,
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s query failed: %s", tier_label, exc)
        mgr.reset()
    return results


def _sync_query_hybrid(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 (local) and L2 (global) — in parallel."""
    mgr = _get_mgr()
    try:
        mgr.connect()
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    where_filter: dict | None = None
    if tech_stack:
        where_filter = {"tech_stack": tech_stack}

    # Query L1 + L2 in parallel (persistent executor — B3)
    l1_future = mgr._query_executor.submit(
        _query_single_tier,
        "L1_LOCAL",
        lambda: mgr.get_l1_direct(workspace_id),
        query,
        n_results,
        where_filter,
    )
    l2_future = mgr._query_executor.submit(
        _query_single_tier,
        "L2_GLOBAL",
        mgr.get_l2_direct,
        query,
        n_results,
        where_filter,
    )

    try:
        l1_results = l1_future.result(timeout=_CHROMA_OP_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("L1 parallel query failed: %s", exc)
        l1_results = []

    try:
        l2_results = l2_future.result(timeout=_CHROMA_OP_TIMEOUT)
    except Exception as exc:  # noqa: BLE001
        logger.warning("L2 parallel query failed: %s", exc)
        l2_results = []

    # Merge & Re-rank by distance
    all_results = l1_results + l2_results
    if not all_results:
        return json.dumps(
            {
                "status": "no_results",
                "message": "No context found in L1 or L2 memory.",
                "suggestion": "Store context first with store_working_context or store_knowledge.",
            },
            indent=2,
            ensure_ascii=False,
        )

    all_results.sort(key=lambda r: r["distance"])
    top_results = all_results[:n_results]

    sections: list[str] = []
    for i, result in enumerate(top_results):
        tier_tag = f"[{result['tier']}]"
        meta = result["metadata"]
        sections.append(
            f"--- Result {i + 1} {tier_tag} ---\n"
            f"Source    : {meta.get('source', 'unknown')}\n"
            f"Stack     : {meta.get('tech_stack', 'general')}\n"
            f"Distance  : {result['distance']}\n"
            f"Stored at : {meta.get('timestamp', 'unknown')}\n\n"
            f"{result['document']}"
        )

    return json.dumps(
        {
            "status": "success",
            "total_results": len(top_results),
            "l1_hits": sum(1 for r in top_results if r["tier"] == "L1_LOCAL"),
            "l2_hits": sum(1 for r in top_results if r["tier"] == "L2_GLOBAL"),
            "tech_stack_filter": tech_stack,
            "results": "\n\n".join(sections),
        },
        indent=2,
        ensure_ascii=False,
    )


def _sync_cleanup_l1(workspace_id: str = "default", days: int = _L1_TTL_DAYS) -> str:
    """Delete L1 records older than *days*."""
    mgr = _get_mgr()
    try:
        collection = mgr.get_l1_direct(workspace_id)
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    try:
        total_before: int = collection.count()
    except Exception as exc:  # noqa: BLE001
        mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to count L1 records: {exc}"},
            ensure_ascii=False,
        )

    if total_before == 0:
        return json.dumps(
            {"status": "skipped", "message": "L1 memory is already empty."},
            ensure_ascii=False,
        )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    try:
        all_records = collection.get(include=["metadatas"])
    except Exception as exc:  # noqa: BLE001
        mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to fetch L1 records: {exc}"},
            ensure_ascii=False,
        )

    old_ids: list[str] = []
    for i, record_id in enumerate(all_records["ids"]):
        meta = all_records["metadatas"][i] if all_records["metadatas"] else {}
        ts = meta.get("timestamp", "")
        if ts and ts < cutoff:
            old_ids.append(record_id)

    if not old_ids:
        return json.dumps(
            {
                "status": "skipped",
                "message": f"No L1 records older than {days} days.",
                "total_records": total_before,
            },
            indent=2,
            ensure_ascii=False,
        )

    try:
        collection.delete(ids=old_ids)
        remaining = collection.count()
    except Exception as exc:  # noqa: BLE001
        mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to delete L1 records: {exc}"},
            ensure_ascii=False,
        )

    return json.dumps(
        {
            "status": "success",
            "tier": "L1",
            "workspace_id": workspace_id,
            "deleted": len(old_ids),
            "remaining": remaining,
            "cutoff_date": cutoff,
        },
        indent=2,
        ensure_ascii=False,
    )


def _sync_memory_stats() -> str:
    """Get memory statistics for L1 and L2 collections."""
    mgr = _get_mgr()
    try:
        client = mgr.connect()
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    try:
        collections = client.list_collections()
    except Exception as exc:  # noqa: BLE001
        mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to list collections: {exc}"},
            ensure_ascii=False,
        )

    l1_stats: dict[str, int] = {}
    l2_count: int = 0

    for col in collections:
        name = col.name if hasattr(col, "name") else str(col)
        try:
            if hasattr(col, "count"):
                count = col.count()
            else:
                col_obj = client.get_collection(name=name)
                count = col_obj.count()
        except Exception:  # noqa: BLE001
            count = -1
        if name.startswith(_L1_PREFIX):
            workspace = name[len(_L1_PREFIX) :]
            l1_stats[workspace] = count
        elif name == _L2_COLLECTION:
            l2_count = count

    return json.dumps(
        {
            "status": "success",
            "l1_workspaces": l1_stats,
            "l1_total_chunks": sum(l1_stats.values()),
            "l2_global_chunks": l2_count,
            "total_collections": len(collections),
        },
        indent=2,
        ensure_ascii=False,
    )


# ---------------------------------------------------------------------------
# Public Async API — Dispatched via _mgr._executor
# ---------------------------------------------------------------------------

_ASYNC_TIMEOUT: int = _CHROMA_OP_TIMEOUT + 5


def _error_json(message: str) -> str:
    """Return a JSON error string (DRY helper for async wrappers)."""
    return json.dumps({"status": "error", "message": message}, ensure_ascii=False)


async def compress_and_store(
    text_data: str,
    metadata_source: str,
    tier: str = "L1",
    workspace_id: str = "default",
    tech_stack: str = "general",
) -> str:
    """Store context into L1 (local) or L2 (global) memory."""
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                mgr._executor,
                lambda: _sync_store(
                    text_data, metadata_source, tier, workspace_id, tech_stack
                ),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        mgr.reset()
        return _error_json(f"store_working_context timed out after {_ASYNC_TIMEOUT}s.")


async def query_memory(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 + L2 with merge & re-rank."""
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                mgr._executor,
                lambda: _sync_query_hybrid(query, workspace_id, tech_stack, n_results),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        mgr.reset()
        return _error_json(f"search_memory timed out after {_ASYNC_TIMEOUT}s.")


async def cleanup_l1(
    workspace_id: str = "default",
    days: int = _L1_TTL_DAYS,
) -> str:
    """Cleanup old L1 records for a workspace."""
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                mgr._executor,
                lambda: _sync_cleanup_l1(workspace_id, days),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        mgr.reset()
        return _error_json(f"cleanup_workspace timed out after {_ASYNC_TIMEOUT}s.")


async def get_memory_stats() -> str:
    """Get L1/L2 memory statistics."""
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(mgr._executor, _sync_memory_stats),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        mgr.reset()
        return _error_json(f"memory_stats timed out after {_ASYNC_TIMEOUT}s.")


# ---------------------------------------------------------------------------
# Quick Recall — Lightweight search for auto-recall tool
# ---------------------------------------------------------------------------


def _sync_quick_recall(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 3,
) -> str:
    """Fast, lightweight recall for auto-recall tool."""
    mgr = _get_mgr()
    try:
        mgr.connect()
    except (ConnectionError, TimeoutError):
        return ""

    where_filter: dict | None = None
    if tech_stack:
        where_filter = {"tech_stack": tech_stack}

    # Query L1 + L2 in parallel (persistent executor)
    l1_future = mgr._query_executor.submit(
        _query_single_tier,
        "L1_LOCAL",
        lambda: mgr.get_l1_direct(workspace_id),
        query,
        n_results,
        where_filter,
    )
    l2_future = mgr._query_executor.submit(
        _query_single_tier,
        "L2_GLOBAL",
        mgr.get_l2_direct,
        query,
        n_results,
        where_filter,
    )

    try:
        l1_results = l1_future.result(timeout=_QUICK_RECALL_TIMEOUT)
    except Exception:  # noqa: BLE001
        l1_results = []
    try:
        l2_results = l2_future.result(timeout=_QUICK_RECALL_TIMEOUT)
    except Exception:  # noqa: BLE001
        l2_results = []

    all_results = l1_results + l2_results
    if not all_results:
        return ""

    all_results.sort(key=lambda r: r["distance"])
    top = all_results[:n_results]

    sections: list[str] = []
    total_len = 0
    for r in top:
        meta = r["metadata"]
        section = (
            f"[{r['tier']}] source={meta.get('source', '?')} "
            f"distance={r['distance']:.3f}\n"
            f"{r['document']}"
        )
        if total_len + len(section) > _QUICK_RECALL_MAX_CHARS:
            break
        sections.append(section)
        total_len += len(section)

    return "\n---\n".join(sections)


async def quick_recall(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 3,
) -> str:
    """Fast context recall for auto-recall tool.

    Short timeout, compact output, never throws.
    """
    mgr = _get_mgr()
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                mgr._executor,
                lambda: _sync_quick_recall(query, workspace_id, tech_stack, n_results),
            ),
            timeout=_QUICK_RECALL_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return ""

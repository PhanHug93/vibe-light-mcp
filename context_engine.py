"""
Context Engine — Hybrid RAG (L1/L2 Memory) via ChromaDB HTTP.

Two-tier memory architecture:
  - **L1 (Local Working Memory)**: Per-workspace, short-term context
    (code files, logs, drafts). Auto-cleanup after 3 days.
  - **L2 (Global Knowledge Brain)**: Cross-workspace, permanent knowledge
    (rules, skills, solved bugs, boilerplate configs).

Connection: ``chromadb.HttpClient`` → background ChromaDB server on port 8888.
This eliminates ``database is locked`` errors across multiple workspaces.

Architecture:
  - **Lazy Init** with ``threading.Lock()`` for thread safety.
  - **Sync/Async separation**: Core ``_sync_*`` functions wrapped by
    ``asyncio.to_thread()`` in public async API.
  - **Federated Search**: Queries L1 + L2 in parallel, merges and
    re-ranks results by distance.

Usage::

    from context_engine import (
        compress_and_store, query_memory, cleanup_l1,
        get_memory_stats,
    )
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHROMA_HOST: str = "localhost"
_CHROMA_PORT: int = 8888

_L1_PREFIX: str = "mcp_local_"
_L2_COLLECTION: str = "mcp_global_knowledge"

_L1_TTL_DAYS: int = 3  # Auto-cleanup threshold for L1

# ---------------------------------------------------------------------------
# Semantic Chunking (kept from v2 — unchanged)
# ---------------------------------------------------------------------------

_SEPARATORS: list[str] = ["\n\n", "\n", ". ", " "]
_DEFAULT_CHUNK_SIZE: int = 1000
_DEFAULT_CHUNK_OVERLAP: int = 150


def recursive_text_split(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """Recursively split *text* at semantic anchor points.

    Priority order: ``\\n\\n`` → ``\\n`` → ``. `` → `` ``
    Preserves code functions, paragraphs, and sentences intact.
    """
    if not text.strip():
        return []
    if len(text) <= chunk_size:
        return [text.strip()]

    seps = separators if separators is not None else list(_SEPARATORS)

    if not seps:
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            start += chunk_size - chunk_overlap
        return chunks

    sep = seps[0]
    remaining_seps = seps[1:]
    segments = text.split(sep)

    merged_chunks: list[str] = []
    current_chunk = ""

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        candidate = f"{current_chunk}{sep}{segment}" if current_chunk else segment
        if len(candidate) <= chunk_size:
            current_chunk = candidate
        else:
            if current_chunk:
                merged_chunks.append(current_chunk.strip())
            if len(segment) > chunk_size:
                merged_chunks.extend(
                    recursive_text_split(segment, chunk_size, chunk_overlap, remaining_seps)
                )
                current_chunk = ""
            else:
                current_chunk = segment

    if current_chunk.strip():
        merged_chunks.append(current_chunk.strip())

    if chunk_overlap > 0 and len(merged_chunks) > 1:
        overlapped: list[str] = [merged_chunks[0]]
        for i in range(1, len(merged_chunks)):
            prev = merged_chunks[i - 1]
            tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            for break_sep in _SEPARATORS:
                idx = tail.find(break_sep)
                if idx != -1:
                    tail = tail[idx + len(break_sep):]
                    break
            overlapped.append(f"{tail.strip()} {merged_chunks[i]}".strip())
        return overlapped

    return merged_chunks


# ---------------------------------------------------------------------------
# ChromaDB Client — Lazy Init (Thread-safe)
# ---------------------------------------------------------------------------

_client: chromadb.HttpClient | None = None
_init_lock: threading.Lock = threading.Lock()
_l2_collection: Collection | None = None
_l1_cache: dict[str, Collection] = {}


def _init_chroma() -> chromadb.HttpClient:
    """Lazy-init ChromaDB HttpClient. Thread-safe via Lock."""
    global _client  # noqa: PLW0603
    if _client is not None:
        return _client

    with _init_lock:
        # Double-check after acquiring lock
        if _client is not None:
            return _client
        try:
            logger.info("Connecting to ChromaDB at %s:%d ...", _CHROMA_HOST, _CHROMA_PORT)
            _client = chromadb.HttpClient(host=_CHROMA_HOST, port=_CHROMA_PORT)
            _client.heartbeat()  # Validate connection
            logger.info("ChromaDB connected successfully")
        except Exception as exc:
            _client = None
            raise ConnectionError(
                f"ChromaDB server not reachable at {_CHROMA_HOST}:{_CHROMA_PORT}. "
                f"Start it with: chroma run --path ~/.mcp_global_db --port {_CHROMA_PORT}\n"
                f"Error: {exc}"
            ) from exc
    return _client


def _get_l1_collection(workspace_id: str) -> Collection:
    """Get or create L1 (local working memory) collection for a workspace."""
    collection_name = f"{_L1_PREFIX}{workspace_id}"
    if collection_name in _l1_cache:
        return _l1_cache[collection_name]

    client = _init_chroma()
    collection = client.get_or_create_collection(name=collection_name)
    _l1_cache[collection_name] = collection
    logger.info("L1 collection ready: %s", collection_name)
    return collection


def _get_l2_collection() -> Collection:
    """Get or create L2 (global knowledge brain) collection."""
    global _l2_collection  # noqa: PLW0603
    if _l2_collection is not None:
        return _l2_collection

    client = _init_chroma()
    _l2_collection = client.get_or_create_collection(name=_L2_COLLECTION)
    logger.info("L2 collection ready: %s", _L2_COLLECTION)
    return _l2_collection


def _workspace_hash(path: str) -> str:
    """Generate short deterministic hash from workspace path."""
    return hashlib.md5(path.encode()).hexdigest()[:8]  # noqa: S324


# ---------------------------------------------------------------------------
# Sync Core Functions
# ---------------------------------------------------------------------------


def _sync_store(
    text_data: str,
    metadata_source: str,
    tier: str = "L1",
    workspace_id: str = "default",
    tech_stack: str = "general",
) -> str:
    """Chunk and store text into L1 or L2 collection.

    Args:
        text_data: Text to store.
        metadata_source: Origin label (file path, URL, etc.).
        tier: ``"L1"`` for local working memory, ``"L2"`` for global knowledge.
        workspace_id: Workspace identifier (used for L1 only).
        tech_stack: Tech stack tag for pre-filtering.

    Returns:
        JSON string with storage result.
    """
    chunks = recursive_text_split(text_data)
    if not chunks:
        return json.dumps(
            {"status": "skipped", "message": "Input text is empty."},
            ensure_ascii=False,
        )

    try:
        if tier == "L2":
            collection = _get_l2_collection()
            collection_name = _L2_COLLECTION
        else:
            collection = _get_l1_collection(workspace_id)
            collection_name = f"{_L1_PREFIX}{workspace_id}"
    except ConnectionError as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    batch_id: str = uuid.uuid4().hex[:8]
    timestamp: str = datetime.now(timezone.utc).isoformat()

    ids = [f"{batch_id}_{i}" for i in range(len(chunks))]
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

    collection.add(documents=chunks, ids=ids, metadatas=metadatas)

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


def _sync_query_hybrid(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 (local) and L2 (global).

    Queries both collections, merges results, re-ranks by distance,
    and returns top N with tier labels.

    Args:
        query: Natural-language query.
        workspace_id: Workspace ID for L1 lookup.
        tech_stack: Optional pre-filter by tech stack.
        n_results: Total results to return after merge.

    Returns:
        JSON string with merged, re-ranked results.
    """
    try:
        _init_chroma()
    except ConnectionError as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    where_filter: dict | None = None
    if tech_stack:
        where_filter = {"tech_stack": tech_stack}

    # --- Query L1 (local workspace) ---
    l1_results: list[dict] = []
    try:
        l1_col = _get_l1_collection(workspace_id)
        if l1_col.count() > 0:
            l1_n = min(n_results, l1_col.count())
            raw_l1 = l1_col.query(
                query_texts=[query], n_results=l1_n, where=where_filter,
            )
            l1_docs = raw_l1["documents"][0] if raw_l1["documents"] else []
            l1_meta = raw_l1["metadatas"][0] if raw_l1["metadatas"] else []
            l1_dist = raw_l1["distances"][0] if raw_l1.get("distances") else []
            for i, doc in enumerate(l1_docs):
                l1_results.append({
                    "tier": "L1_LOCAL",
                    "document": doc,
                    "metadata": l1_meta[i] if i < len(l1_meta) else {},
                    "distance": l1_dist[i] if i < len(l1_dist) else 999.0,
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("L1 query failed: %s", exc)

    # --- Query L2 (global knowledge) ---
    l2_results: list[dict] = []
    try:
        l2_col = _get_l2_collection()
        if l2_col.count() > 0:
            l2_n = min(n_results, l2_col.count())
            raw_l2 = l2_col.query(
                query_texts=[query], n_results=l2_n, where=where_filter,
            )
            l2_docs = raw_l2["documents"][0] if raw_l2["documents"] else []
            l2_meta = raw_l2["metadatas"][0] if raw_l2["metadatas"] else []
            l2_dist = raw_l2["distances"][0] if raw_l2.get("distances") else []
            for i, doc in enumerate(l2_docs):
                l2_results.append({
                    "tier": "L2_GLOBAL",
                    "document": doc,
                    "metadata": l2_meta[i] if i < len(l2_meta) else {},
                    "distance": l2_dist[i] if i < len(l2_dist) else 999.0,
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("L2 query failed: %s", exc)

    # --- Merge & Re-rank by distance ---
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

    # --- Format output ---
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
    """Delete L1 records older than *days*.

    Args:
        workspace_id: Workspace to clean up.
        days: Records older than this will be deleted (default 3).

    Returns:
        JSON string with cleanup result.
    """
    try:
        collection = _get_l1_collection(workspace_id)
    except ConnectionError as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    total_before: int = collection.count()
    if total_before == 0:
        return json.dumps(
            {"status": "skipped", "message": "L1 memory is already empty."},
            ensure_ascii=False,
        )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    # Fetch all and filter (compatible with all ChromaDB versions)
    all_records = collection.get(include=["metadatas"])
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

    collection.delete(ids=old_ids)

    return json.dumps(
        {
            "status": "success",
            "tier": "L1",
            "workspace_id": workspace_id,
            "deleted": len(old_ids),
            "remaining": collection.count(),
            "cutoff_date": cutoff,
        },
        indent=2,
        ensure_ascii=False,
    )


def _sync_memory_stats() -> str:
    """Get memory statistics for L1 and L2 collections.

    Returns:
        JSON with collection counts and sizes.
    """
    try:
        client = _init_chroma()
    except ConnectionError as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    collections = client.list_collections()

    l1_stats: dict[str, int] = {}
    l2_count: int = 0

    for col in collections:
        name = col.name if hasattr(col, "name") else str(col)
        count = client.get_collection(name).count()
        if name.startswith(_L1_PREFIX):
            workspace = name[len(_L1_PREFIX):]
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
# Public Async API (Wrappers for FastMCP)
# ---------------------------------------------------------------------------


async def compress_and_store(
    text_data: str,
    metadata_source: str,
    tier: str = "L1",
    workspace_id: str = "default",
    tech_stack: str = "general",
) -> str:
    """Store context into L1 (local) or L2 (global) memory.

    Runs sync ChromaDB operations in a background thread.
    """
    return await asyncio.to_thread(
        _sync_store, text_data, metadata_source, tier, workspace_id, tech_stack,
    )


async def query_memory(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 + L2 with merge & re-rank.

    Runs sync ChromaDB operations in a background thread.
    """
    return await asyncio.to_thread(
        _sync_query_hybrid, query, workspace_id, tech_stack, n_results,
    )


async def cleanup_l1(
    workspace_id: str = "default",
    days: int = _L1_TTL_DAYS,
) -> str:
    """Cleanup old L1 records for a workspace.

    Runs sync ChromaDB operations in a background thread.
    """
    return await asyncio.to_thread(_sync_cleanup_l1, workspace_id, days)


async def get_memory_stats() -> str:
    """Get L1/L2 memory statistics.

    Runs sync ChromaDB operations in a background thread.
    """
    return await asyncio.to_thread(_sync_memory_stats)

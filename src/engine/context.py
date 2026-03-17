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
  - **_ChromaManager** class with dedicated ``ThreadPoolExecutor`` for
    isolation from asyncio's default pool — prevents thread-pool starvation.
  - **Per-operation timeouts** on every ChromaDB call — no more infinite blocks.
  - **Auto-reconnect**: stale clients/caches are invalidated on failure and
    recreated on the next call.
  - **Federated Search**: Queries L1 + L2, merges and re-ranks by distance.

Usage::

    from context_engine import (
        compress_and_store, query_memory, cleanup_l1,
        get_memory_stats,
    )
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
import logging
import threading
import time
import typing
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

_CHROMA_CONNECT_TIMEOUT: int = 5   # seconds — initial connection + heartbeat
_CHROMA_OP_TIMEOUT: int = 15       # seconds — per ChromaDB operation
_CHROMA_POOL_SIZE: int = 4         # dedicated thread-pool workers
_CHROMA_HEARTBEAT_INTERVAL: int = 30  # seconds — proactive staleness check

_EMBEDDING_MODEL: str = "all-MiniLM-L12-v2"  # 384d, 12 layers — better than default L6
_QUICK_RECALL_TIMEOUT: int = 5     # seconds — fast timeout for auto-recall
_QUICK_RECALL_MAX_CHARS: int = 3000  # truncate auto-recall output


# ---------------------------------------------------------------------------
# Embedding Function (with graceful fallback)
# ---------------------------------------------------------------------------

_embedding_fn_cache = None


def _get_embedding_fn():
    """Return the best available embedding function.

    Priority:
    1. ``sentence-transformers`` with ``all-MiniLM-L12-v2`` (12 layers, better quality)
    2. ChromaDB default ONNX-based ``all-MiniLM-L6-v2`` (fallback)

    The result is cached after first call.
    """
    global _embedding_fn_cache  # noqa: PLW0603
    if _embedding_fn_cache is not None:
        return _embedding_fn_cache

    try:
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )
        _embedding_fn_cache = SentenceTransformerEmbeddingFunction(
            model_name=_EMBEDDING_MODEL,
        )
        logger.info("Embedding model: %s (sentence-transformers)", _EMBEDDING_MODEL)
    except Exception:  # noqa: BLE001
        # Fallback to ChromaDB default (all-MiniLM-L6-v2 via onnxruntime)
        _embedding_fn_cache = None
        logger.info("Embedding model: default ONNX (sentence-transformers not available)")

    return _embedding_fn_cache

# ---------------------------------------------------------------------------
# Semantic Chunking — delegated to text_splitter (SRP)
# ---------------------------------------------------------------------------

from src.utils.text_splitter import recursive_text_split  # noqa: E402


# ---------------------------------------------------------------------------
# ChromaDB Connection Manager (Thread-safe, Timeout-protected)
# ---------------------------------------------------------------------------


class _ChromaManager:
    """Thread-safe ChromaDB client with dedicated pool, timeouts & auto-reconnect.

    Key design decisions
    --------------------
    * **Dedicated ThreadPoolExecutor** (`_CHROMA_POOL_SIZE` workers) keeps
      ChromaDB I/O isolated from asyncio's default pool — a slow or dead
      ChromaDB can no longer starve `run_terminal_command` and other tools.
    * **Per-operation timeout** via ``concurrent.futures.Future.result(timeout)``
      guarantees every ChromaDB call finishes (or raises) within
      ``_CHROMA_OP_TIMEOUT`` seconds.  Used only at the **outer** async→sync
      boundary.  Sync functions that already run inside the executor call
      ChromaDB directly via ``_get_l1_direct`` / ``_get_l2_direct`` to
      avoid nested executor submissions and potential deadlock.
    * **Auto-reconnect**: on *any* ChromaDB failure the client and all cached
      collections are invalidated.  The next call transparently creates a
      fresh connection.
    * **Background health checker** daemon validates the connection every
      ``_CHROMA_HEARTBEAT_INTERVAL`` seconds — off the hot path.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: chromadb.HttpClient | None = None
        self._l2_collection: Collection | None = None
        self._l1_cache: dict[str, Collection] = {}
        self._healthy = True  # set by background health checker
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=_CHROMA_POOL_SIZE,
            thread_name_prefix="chroma",
        )
        # Start background health checker daemon.
        self._health_thread = threading.Thread(
            target=self._background_health_loop, daemon=True,
            name="chroma-health",
        )
        self._health_thread.start()

    # ------------------------------------------------------------------
    # Background health checker (off the hot path)
    # ------------------------------------------------------------------

    def _background_health_loop(self) -> None:
        """Periodically check ChromaDB liveness in a background thread."""
        while True:
            time.sleep(_CHROMA_HEARTBEAT_INTERVAL)
            if self._client is None:
                continue
            try:
                self._client.heartbeat()
                self._healthy = True
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Background heartbeat failed — resetting connection.",
                )
                self._healthy = False
                self.reset()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def _connect(self) -> chromadb.HttpClient:
        """Return a live HttpClient, creating one if necessary.

        * Lock scope is minimal — only held during client creation.
        * ``heartbeat()`` is called directly to validate liveness.
        """
        if self._client is not None:
            return self._client

        with self._lock:
            # Double-check after acquiring lock.
            if self._client is not None:
                return self._client

            logger.info(
                "Connecting to ChromaDB at %s:%d ...", _CHROMA_HOST, _CHROMA_PORT,
            )
            try:
                client = chromadb.HttpClient(
                    host=_CHROMA_HOST, port=_CHROMA_PORT,
                )
                # Validate connection with a timeout.
                fut = self._executor.submit(client.heartbeat)
                fut.result(timeout=_CHROMA_CONNECT_TIMEOUT)
                self._client = client
                self._healthy = True
                logger.info("ChromaDB connected successfully")
            except concurrent.futures.TimeoutError:
                raise ConnectionError(
                    f"ChromaDB heartbeat timed out after {_CHROMA_CONNECT_TIMEOUT}s. "
                    f"Server at {_CHROMA_HOST}:{_CHROMA_PORT} may be overloaded."
                )
            except Exception as exc:
                raise ConnectionError(
                    f"ChromaDB not reachable at {_CHROMA_HOST}:{_CHROMA_PORT}. "
                    f"Start it: chroma run --path ~/.mcp_global_db --port {_CHROMA_PORT}\n"
                    f"Error: {exc}"
                ) from exc
        return self._client

    # ------------------------------------------------------------------
    # Timeout helper (outer boundary ONLY — do NOT call from sync fns)
    # ------------------------------------------------------------------

    def run_with_timeout(
        self,
        fn: callable,
        *args,
        timeout: int = _CHROMA_OP_TIMEOUT,
        **kwargs,
    ):
        """Execute *fn* in the dedicated thread pool with a hard timeout.

        ⚠ Use ONLY at the async→sync boundary.  Sync functions that
        already run inside the executor must call ChromaDB directly
        (via ``_get_l1_direct`` / ``_get_l2_direct``) to avoid nested
        executor submissions and deadlock.
        """
        try:
            fut = self._executor.submit(fn, *args, **kwargs)
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(
                "ChromaDB operation timed out after %ds: %s", timeout, fn.__name__,
            )
            self.reset()
            raise TimeoutError(
                f"ChromaDB operation '{fn.__name__}' timed out after {timeout}s."
            )
        except Exception:
            # Any connection-level error → invalidate everything.
            self.reset()
            raise

    # ------------------------------------------------------------------
    # Direct collection accessors (for use INSIDE executor — no nesting)
    # ------------------------------------------------------------------

    def _get_l1_direct(self, workspace_id: str) -> Collection:
        """Get or create an L1 collection — direct call, no executor.

        Safe to call from sync functions already running inside the
        executor.  Checks cached value first, then calls ChromaDB
        directly.
        """
        collection_name = f"{_L1_PREFIX}{workspace_id}"
        if collection_name in self._l1_cache and self._healthy:
            return self._l1_cache[collection_name]

        client = self._connect()
        ef = _get_embedding_fn()
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
        ) if ef else client.get_or_create_collection(name=collection_name)
        self._l1_cache[collection_name] = collection
        logger.info("L1 collection ready: %s", collection_name)
        return collection

    def _get_l2_direct(self) -> Collection:
        """Get or create the L2 collection — direct call, no executor.

        Safe to call from sync functions already running inside the
        executor.
        """
        if self._l2_collection is not None and self._healthy:
            return self._l2_collection

        client = self._connect()
        ef = _get_embedding_fn()
        self._l2_collection = client.get_or_create_collection(
            name=_L2_COLLECTION,
            embedding_function=ef,
        ) if ef else client.get_or_create_collection(name=_L2_COLLECTION)
        logger.info("L2 collection ready: %s", _L2_COLLECTION)
        return self._l2_collection

    # ------------------------------------------------------------------
    # Legacy accessors (kept for external callers; use executor)
    # ------------------------------------------------------------------

    def get_l1(self, workspace_id: str) -> Collection:
        """Get or create an L1 collection via executor (for external use)."""
        collection_name = f"{_L1_PREFIX}{workspace_id}"
        if collection_name in self._l1_cache and self._healthy:
            return self._l1_cache[collection_name]

        client = self._connect()
        collection = self.run_with_timeout(
            client.get_or_create_collection,
            name=collection_name,
            embedding_function=_get_embedding_fn(),
        )
        self._l1_cache[collection_name] = collection
        return collection

    def get_l2(self) -> Collection:
        """Get or create the L2 collection via executor (for external use)."""
        if self._l2_collection is not None and self._healthy:
            return self._l2_collection

        client = self._connect()
        self._l2_collection = self.run_with_timeout(
            client.get_or_create_collection,
            name=_L2_COLLECTION,
            embedding_function=_get_embedding_fn(),
        )
        return self._l2_collection

    # ------------------------------------------------------------------
    # Reset (auto-reconnect support)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Invalidate client and all cached collections.

        Called automatically on failure.  The next operation will
        transparently create a fresh connection.
        """
        with self._lock:
            self._client = None
            self._l2_collection = None
            self._l1_cache.clear()
            self._healthy = False
        logger.warning("ChromaDB connection reset — will reconnect on next call.")


# Singleton manager instance.
_mgr = _ChromaManager()


def _workspace_hash(path: str) -> str:
    """Generate short deterministic hash from workspace path."""
    return hashlib.md5(path.encode()).hexdigest()[:8]  # noqa: S324


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
    chunks = recursive_text_split(text_data)
    if not chunks:
        return json.dumps(
            {"status": "skipped", "message": "Input text is empty."},
            ensure_ascii=False,
        )

    try:
        if tier == "L2":
            collection = _mgr._get_l2_direct()
            collection_name = _L2_COLLECTION
        else:
            collection = _mgr._get_l1_direct(workspace_id)
            collection_name = f"{_L1_PREFIX}{workspace_id}"
    except (ConnectionError, TimeoutError) as exc:
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

    try:
        collection.add(documents=chunks, ids=ids, metadatas=metadatas)
    except Exception as exc:  # noqa: BLE001
        _mgr.reset()
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
    collection_getter: typing.Callable[[], Collection],
    query: str,
    n_results: int,
    where_filter: dict | None,
) -> list[dict]:
    """Query a single tier (L1 or L2) and return formatted results.

    Called directly — no executor nesting.
    """
    results: list[dict] = []
    try:
        col = collection_getter()
        count = col.count()
        if count > 0:
            n = min(n_results, count)
            raw = col.query(
                query_texts=[query], n_results=n, where=where_filter,
            )
            docs = raw["documents"][0] if raw["documents"] else []
            metas = raw["metadatas"][0] if raw["metadatas"] else []
            dists = raw["distances"][0] if raw.get("distances") else []
            for i, doc in enumerate(docs):
                results.append({
                    "tier": tier_label,
                    "document": doc,
                    "metadata": metas[i] if i < len(metas) else {},
                    "distance": dists[i] if i < len(dists) else 999.0,
                })
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s query failed: %s", tier_label, exc)
        _mgr.reset()
    return results


def _sync_query_hybrid(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 (local) and L2 (global) — in parallel.

    L1 and L2 are queried concurrently via a short-lived 2-worker pool.
    Direct ChromaDB calls — no nested executor submissions.
    """
    try:
        _mgr._connect()
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    where_filter: dict | None = None
    if tech_stack:
        where_filter = {"tech_stack": tech_stack}

    # --- Query L1 + L2 in parallel ---
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="query",
    ) as pool:
        l1_future = pool.submit(
            _query_single_tier,
            "L1_LOCAL",
            lambda: _mgr._get_l1_direct(workspace_id),
            query, n_results, where_filter,
        )
        l2_future = pool.submit(
            _query_single_tier,
            "L2_GLOBAL",
            _mgr._get_l2_direct,
            query, n_results, where_filter,
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

    Runs inside ``_mgr._executor`` — calls ChromaDB directly.
    """
    try:
        collection = _mgr._get_l1_direct(workspace_id)
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    try:
        total_before: int = collection.count()
    except Exception as exc:  # noqa: BLE001
        _mgr.reset()
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

    # Fetch IDs + metadatas only (no documents — saves memory/bandwidth)
    try:
        all_records = collection.get(include=["metadatas"])
    except Exception as exc:  # noqa: BLE001
        _mgr.reset()
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
        _mgr.reset()
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
    """Get memory statistics for L1 and L2 collections.

    Runs inside ``_mgr._executor`` — calls ChromaDB directly.
    Fixed N+1 query: uses collection objects from list_collections directly.
    """
    try:
        client = _mgr._connect()
    except (ConnectionError, TimeoutError) as exc:
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

    try:
        collections = client.list_collections()
    except Exception as exc:  # noqa: BLE001
        _mgr.reset()
        return json.dumps(
            {"status": "error", "message": f"Failed to list collections: {exc}"},
            ensure_ascii=False,
        )

    l1_stats: dict[str, int] = {}
    l2_count: int = 0

    for col in collections:
        name = col.name if hasattr(col, "name") else str(col)
        try:
            # Use collection directly — no redundant get_collection() call
            if hasattr(col, "count"):
                count = col.count()
            else:
                col_obj = client.get_collection(name=name)
                count = col_obj.count()
        except Exception:  # noqa: BLE001
            count = -1  # indicate failure without blocking
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
# Public Async API — Dispatched via _mgr._executor (isolated from default pool)
# ---------------------------------------------------------------------------

_ASYNC_TIMEOUT: int = _CHROMA_OP_TIMEOUT + 5  # slightly longer than per-op timeout


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
    """Store context into L1 (local) or L2 (global) memory.

    Dispatched to ``_mgr._executor`` (dedicated pool) with an outer
    ``asyncio.wait_for`` timeout so the event loop is never blocked.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _mgr._executor,
                lambda: _sync_store(text_data, metadata_source, tier, workspace_id, tech_stack),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _mgr.reset()
        return _error_json(f"store_working_context timed out after {_ASYNC_TIMEOUT}s.")


async def query_memory(
    query: str,
    workspace_id: str = "default",
    tech_stack: str | None = None,
    n_results: int = 5,
) -> str:
    """Federated search across L1 + L2 with merge & re-rank.

    Dispatched to ``_mgr._executor`` with outer async timeout.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _mgr._executor,
                lambda: _sync_query_hybrid(query, workspace_id, tech_stack, n_results),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _mgr.reset()
        return _error_json(f"search_memory timed out after {_ASYNC_TIMEOUT}s.")


async def cleanup_l1(
    workspace_id: str = "default",
    days: int = _L1_TTL_DAYS,
) -> str:
    """Cleanup old L1 records for a workspace.

    Dispatched to ``_mgr._executor`` with outer async timeout.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _mgr._executor,
                lambda: _sync_cleanup_l1(workspace_id, days),
            ),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _mgr.reset()
        return _error_json(f"cleanup_workspace timed out after {_ASYNC_TIMEOUT}s.")


async def get_memory_stats() -> str:
    """Get L1/L2 memory statistics.

    Dispatched to ``_mgr._executor`` with outer async timeout.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_mgr._executor, _sync_memory_stats),
            timeout=_ASYNC_TIMEOUT,
        )
    except asyncio.TimeoutError:
        _mgr.reset()
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
    """Fast, lightweight recall for auto-recall tool.

    Similar to ``_sync_query_hybrid`` but:
    - Returns compact text instead of verbose JSON
    - Truncates output to ``_QUICK_RECALL_MAX_CHARS``
    - Designed to never block the agent
    """
    try:
        _mgr._connect()
    except (ConnectionError, TimeoutError):
        return ""  # silent fail — no context is better than blocking

    where_filter: dict | None = None
    if tech_stack:
        where_filter = {"tech_stack": tech_stack}

    # Query L1 + L2 in parallel (reuse existing helper)
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=2, thread_name_prefix="recall",
    ) as pool:
        l1_future = pool.submit(
            _query_single_tier,
            "L1_LOCAL",
            lambda: _mgr._get_l1_direct(workspace_id),
            query, n_results, where_filter,
        )
        l2_future = pool.submit(
            _query_single_tier,
            "L2_GLOBAL",
            _mgr._get_l2_direct,
            query, n_results, where_filter,
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

    # Sort by distance, format compactly
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
    Returns empty string if no context found or on error.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(
                _mgr._executor,
                lambda: _sync_quick_recall(query, workspace_id, tech_stack, n_results),
            ),
            timeout=_QUICK_RECALL_TIMEOUT,
        )
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001
        return ""  # silent fail — never block the agent

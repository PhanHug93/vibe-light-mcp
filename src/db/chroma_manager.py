"""ChromaDB Connection Manager — Thread-safe, Timeout-protected.

Extracted from ``src/engine/context.py`` — single responsibility:
manage the ChromaDB HTTP client lifecycle, connection pooling,
health checks, and collection access.

Usage::

    from src.db.chroma_manager import get_manager

    mgr = get_manager()
    collection = mgr.run_with_timeout(mgr._get_l1_direct, workspace_id)
"""
from __future__ import annotations

import concurrent.futures
import logging
import threading
import time
from collections import OrderedDict

import chromadb
from chromadb.api.models.Collection import Collection

from src.config import (
    CHROMA_HOST,
    CHROMA_PORT,
    CHROMA_CONNECT_TIMEOUT,
    CHROMA_OP_TIMEOUT,
    CHROMA_POOL_SIZE,
    CHROMA_HEARTBEAT_INTERVAL,
    L1_PREFIX,
    L2_COLLECTION,
)
from src.db.embedding import get_embedding_fn

logger = logging.getLogger(__name__)


class ChromaManager:
    """Thread-safe ChromaDB client with dedicated pool, timeouts & auto-reconnect.

    Key design decisions
    --------------------
    * **Dedicated ThreadPoolExecutor** (``CHROMA_POOL_SIZE`` workers) keeps
      ChromaDB I/O isolated from asyncio's default pool — a slow or dead
      ChromaDB can no longer starve ``run_terminal_command`` and other tools.
    * **Per-operation timeout** via ``concurrent.futures.Future.result(timeout)``
      guarantees every ChromaDB call finishes (or raises) within
      ``CHROMA_OP_TIMEOUT`` seconds.
    * **Auto-reconnect**: on *any* ChromaDB failure the client and all cached
      collections are invalidated.  The next call transparently creates a
      fresh connection.
    * **Persistent query executor** (2 workers) for L1+L2 parallel queries —
      avoids thread churn from creating/destroying pools per query.
    * **Background health checker** daemon validates the connection every
      ``CHROMA_HEARTBEAT_INTERVAL`` seconds — off the hot path.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._client: chromadb.HttpClient | None = None
        self._l2_collection: Collection | None = None
        self._l1_cache: OrderedDict[str, Collection] = OrderedDict()
        self._l1_cache_max: int = 50  # LRU eviction threshold
        self._healthy = True
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=CHROMA_POOL_SIZE,
            thread_name_prefix="chroma",
        )
        self._query_executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=2,
            thread_name_prefix="query",
        )
        self._health_thread = threading.Thread(
            target=self._background_health_loop, daemon=True,
            name="chroma-health",
        )
        self._health_thread.start()

    # ------------------------------------------------------------------
    # Background health checker
    # ------------------------------------------------------------------

    def _background_health_loop(self) -> None:
        """Periodically check ChromaDB liveness in a background thread."""
        while True:
            time.sleep(CHROMA_HEARTBEAT_INTERVAL)
            if self._client is None:
                continue
            try:
                self._client.heartbeat()
                self._healthy = True
            except Exception:  # noqa: BLE001
                logger.warning("Background heartbeat failed — resetting connection.")
                self._healthy = False
                self.reset()

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> chromadb.HttpClient:
        """Return a live HttpClient, creating one if necessary.

        ⚠ ``heartbeat()`` (network call) runs OUTSIDE the lock to prevent
        thread starvation when ChromaDB is slow.  Multiple threads may
        race to create+validate a client — first to finish wins;
        extra clients are discarded (harmless redundancy vs. total block).

        ⚠ This method is called from within executor workers.  It must
        NOT submit work back onto ``self._executor``.
        """
        # Fast path: already connected
        if self._client is not None:
            return self._client

        # Slow path: create client under lock (fast, no network)
        with self._lock:
            if self._client is not None:
                return self._client
            logger.info("Connecting to ChromaDB at %s:%d ...", CHROMA_HOST, CHROMA_PORT)

        # --- Network call OUTSIDE lock ---
        # Multiple threads may reach here simultaneously — that's OK.
        # Each creates and validates independently; first to finish wins.
        try:
            client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
            client.heartbeat()  # Slow network call — NOT under lock!
        except Exception as exc:
            raise ConnectionError(
                f"ChromaDB not reachable at {CHROMA_HOST}:{CHROMA_PORT}. "
                f"Start it: chroma run --path ~/.mcp_global_db --port {CHROMA_PORT}\n"
                f"Error: {exc}"
            ) from exc

        # Assign under lock (fast pointer swap)
        with self._lock:
            if self._client is None:  # First thread wins
                self._client = client
                self._healthy = True
                logger.info("ChromaDB connected successfully")
            # else: another thread already connected — discard our client

        return self._client

    # ------------------------------------------------------------------
    # Timeout helper (outer boundary ONLY)
    # ------------------------------------------------------------------

    def run_with_timeout(
        self,
        fn: callable,
        *args,
        timeout: int = CHROMA_OP_TIMEOUT,
        **kwargs,
    ):
        """Execute *fn* in the dedicated thread pool with a hard timeout.

        ⚠ Use ONLY at the async→sync boundary.  Sync functions that
        already run inside the executor must call ChromaDB directly
        (via ``get_l1_direct`` / ``get_l2_direct``) to avoid nested
        executor submissions and deadlock.
        """
        try:
            fut = self._executor.submit(fn, *args, **kwargs)
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error("ChromaDB operation timed out after %ds: %s", timeout, fn.__name__)
            self.reset()
            raise TimeoutError(
                f"ChromaDB operation '{fn.__name__}' timed out after {timeout}s."
            )
        except Exception:
            self.reset()
            raise

    # ------------------------------------------------------------------
    # Direct collection accessors (for use INSIDE executor — no nesting)
    # ------------------------------------------------------------------

    def get_l1_direct(self, workspace_id: str) -> Collection:
        """Get or create an L1 collection — direct call, no executor.

        Thread-safe: all ``_l1_cache`` mutations protected by ``self._lock``.
        """
        collection_name = f"{L1_PREFIX}{workspace_id}"

        # Fast path: check cache under lock (microseconds)
        with self._lock:
            if collection_name in self._l1_cache and self._healthy:
                self._l1_cache.move_to_end(collection_name)
                return self._l1_cache[collection_name]

        # Slow path: create collection (outside lock — network I/O)
        client = self.connect()
        ef = get_embedding_fn()
        collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=ef,
        ) if ef else client.get_or_create_collection(name=collection_name)

        # Assign under lock (fast pointer swap + LRU eviction)
        with self._lock:
            if len(self._l1_cache) >= self._l1_cache_max:
                self._l1_cache.popitem(last=False)
            self._l1_cache[collection_name] = collection

        logger.info("L1 collection ready: %s", collection_name)
        return collection

    def get_l2_direct(self) -> Collection:
        """Get or create the L2 collection — direct call, no executor."""
        if self._l2_collection is not None and self._healthy:
            return self._l2_collection

        client = self.connect()
        ef = get_embedding_fn()
        self._l2_collection = client.get_or_create_collection(
            name=L2_COLLECTION,
            embedding_function=ef,
        ) if ef else client.get_or_create_collection(name=L2_COLLECTION)
        logger.info("L2 collection ready: %s", L2_COLLECTION)
        return self._l2_collection

    # ------------------------------------------------------------------
    # Legacy accessors (kept for external callers; use executor)
    # ------------------------------------------------------------------

    def get_l1(self, workspace_id: str) -> Collection:
        """Get or create an L1 collection via executor (for external use)."""
        collection_name = f"{L1_PREFIX}{workspace_id}"
        if collection_name in self._l1_cache and self._healthy:
            return self._l1_cache[collection_name]

        client = self.connect()
        collection = self.run_with_timeout(
            client.get_or_create_collection,
            name=collection_name,
            embedding_function=get_embedding_fn(),
        )
        self._l1_cache[collection_name] = collection
        return collection

    def get_l2(self) -> Collection:
        """Get or create the L2 collection via executor (for external use)."""
        if self._l2_collection is not None and self._healthy:
            return self._l2_collection

        client = self.connect()
        self._l2_collection = self.run_with_timeout(
            client.get_or_create_collection,
            name=L2_COLLECTION,
            embedding_function=get_embedding_fn(),
        )
        return self._l2_collection

    # ------------------------------------------------------------------
    # Reset (auto-reconnect support)
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Invalidate client and all cached collections."""
        with self._lock:
            self._client = None
            self._l2_collection = None
            self._l1_cache.clear()
            self._healthy = False
        logger.warning("ChromaDB connection reset — will reconnect on next call.")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: ChromaManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> ChromaManager:
    """Return the singleton ChromaManager instance."""
    global _manager  # noqa: PLW0603
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is None:
            _manager = ChromaManager()
    return _manager

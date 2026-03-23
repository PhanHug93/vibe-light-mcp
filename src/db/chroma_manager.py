"""ChromaDB Connection Manager — Thread-safe, Timeout-protected, Auto-retry.

Extracted from ``src/engine/context.py`` — single responsibility:
manage the ChromaDB HTTP client lifecycle, connection pooling,
health checks, and collection access.

Key design decisions
--------------------
* **Dedicated ThreadPoolExecutor** (``CHROMA_POOL_SIZE`` workers) keeps
  ChromaDB I/O isolated from asyncio's default pool — a slow or dead
  ChromaDB can no longer starve ``run_terminal_command`` and other tools.
* **Per-operation timeout** via ``concurrent.futures.Future.result(timeout)``
  guarantees every ChromaDB call finishes (or raises) within
  ``CHROMA_OP_TIMEOUT`` seconds.
* **Exponential backoff retry** (max 3 attempts) absorbs transient
  network glitches before resetting the entire connection.
* **Auto-reconnect**: on persistent failure the client and all cached
  collections are invalidated.  The next call transparently creates a
  fresh connection.
* **Cosine distance**: all collections use ``cosine`` similarity — the
  standard for semantic search with normalized embeddings.
* **Graceful shutdown**: ``atexit`` hook ensures thread pools are cleaned up.

Usage::

    from src.db.chroma_manager import get_manager

    mgr = get_manager()
    collection = mgr.run_with_timeout(mgr.get_l1_direct, workspace_id)
"""

from __future__ import annotations

import atexit
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
    CHROMA_OP_TIMEOUT,
    CHROMA_POOL_SIZE,
    CHROMA_HEARTBEAT_INTERVAL,
    CHROMA_DISTANCE_FN,
    L1_PREFIX,
    L2_COLLECTION,
)
from src.db.embedding import get_embedding_fn

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_RETRIES: int = 3
"""Maximum retry attempts for transient ChromaDB failures."""

_RETRY_BACKOFF_BASE: float = 0.5
"""Base delay (seconds) for exponential backoff: 0.5s → 1s → 2s."""

_COLLECTION_METADATA: dict = {"hnsw:space": CHROMA_DISTANCE_FN}
"""Metadata applied to every new collection — enforces cosine distance."""


class ChromaManager:
    """Thread-safe ChromaDB client with dedicated pool, timeouts & auto-reconnect."""

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
            target=self._background_health_loop,
            daemon=True,
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
            if CHROMA_HOST not in ("localhost", "127.0.0.1", "::1"):
                logger.warning(
                    "⚠ ChromaDB at %s:%d is NOT localhost — memory data is "
                    "accessible to anyone on the network. Set "
                    "MCP_CHROMA_HOST=localhost for production use.",
                    CHROMA_HOST,
                    CHROMA_PORT,
                )

        # --- Network call OUTSIDE lock ---
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
    # Retry helper (exponential backoff)
    # ------------------------------------------------------------------

    @staticmethod
    def _retry(
        fn: callable,
        *args,
        max_retries: int = _MAX_RETRIES,
        backoff_base: float = _RETRY_BACKOFF_BASE,
        **kwargs,
    ):
        """Execute *fn* with exponential backoff retry on transient failures.

        Retry sequence: immediate → 0.5s → 1s → fail.
        Only retries on Exception (not TimeoutError from run_with_timeout).
        """
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = backoff_base * (2**attempt)
                    logger.warning(
                        "ChromaDB retry %d/%d for %s (backoff %.1fs): %s",
                        attempt + 1,
                        max_retries,
                        fn.__name__,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

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

        Includes retry with exponential backoff before raising.
        """
        try:
            fut = self._executor.submit(
                self._retry,
                fn,
                *args,
                **kwargs,
            )
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            logger.error(
                "ChromaDB operation timed out after %ds: %s", timeout, fn.__name__
            )
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
        Uses cosine distance for semantic search consistency.
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
        collection = (
            client.get_or_create_collection(
                name=collection_name,
                embedding_function=ef,
                metadata=_COLLECTION_METADATA,
            )
            if ef
            else client.get_or_create_collection(
                name=collection_name,
                metadata=_COLLECTION_METADATA,
            )
        )

        # Assign under lock (fast pointer swap + LRU eviction)
        with self._lock:
            if len(self._l1_cache) >= self._l1_cache_max:
                self._l1_cache.popitem(last=False)
            self._l1_cache[collection_name] = collection

        logger.info("L1 collection ready: %s", collection_name)
        return collection

    def get_l2_direct(self) -> Collection:
        """Get or create the L2 collection — direct call, no executor.

        Uses cosine distance for semantic search consistency.
        """
        if self._l2_collection is not None and self._healthy:
            return self._l2_collection

        client = self.connect()
        ef = get_embedding_fn()
        self._l2_collection = (
            client.get_or_create_collection(
                name=L2_COLLECTION,
                embedding_function=ef,
                metadata=_COLLECTION_METADATA,
            )
            if ef
            else client.get_or_create_collection(
                name=L2_COLLECTION,
                metadata=_COLLECTION_METADATA,
            )
        )
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
            metadata=_COLLECTION_METADATA,
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
            metadata=_COLLECTION_METADATA,
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

    # ------------------------------------------------------------------
    # Graceful shutdown
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Shutdown thread pools gracefully.

        Called via ``atexit`` to ensure clean process exit without
        lingering threads or pending futures.
        """
        logger.info("ChromaManager shutting down thread pools...")
        self._executor.shutdown(wait=False)
        self._query_executor.shutdown(wait=False)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_manager: ChromaManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> ChromaManager:
    """Return the singleton ChromaManager instance.

    Registers ``atexit`` shutdown on first creation.
    """
    global _manager  # noqa: PLW0603
    if _manager is not None:
        return _manager
    with _manager_lock:
        if _manager is None:
            _manager = ChromaManager()
            atexit.register(_manager.shutdown)
    return _manager

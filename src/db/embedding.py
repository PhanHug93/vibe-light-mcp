"""Embedding function management (thread-safe, with graceful fallback).

Extracted from ``src/engine/context.py`` — single responsibility:
manage the sentence-transformer / ONNX embedding model lifecycle.

Usage::

    from src.db.embedding import get_embedding_fn, pre_warm_embedding

    # At startup (before event loop)
    pre_warm_embedding()

    # During operation
    ef = get_embedding_fn()  # cached, thread-safe
"""
from __future__ import annotations

import logging
import threading

from src.config import EMBEDDING_MODEL

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe embedding singleton
# ---------------------------------------------------------------------------

_embedding_fn_cache = None
_embedding_lock = threading.Lock()
_embedding_initialized = False


def get_embedding_fn():
    """Return the best available embedding function (thread-safe).

    Priority:
    1. ``sentence-transformers`` with model from config (12 layers, better quality)
    2. ChromaDB default ONNX-based ``all-MiniLM-L6-v2`` (fallback)

    The result is cached after first call.  Thread-safe via double-checked locking.
    """
    global _embedding_fn_cache, _embedding_initialized  # noqa: PLW0603

    # Fast path: already initialized (no lock needed)
    if _embedding_initialized:
        return _embedding_fn_cache

    with _embedding_lock:
        # Double-checked locking
        if _embedding_initialized:
            return _embedding_fn_cache

        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
            _embedding_fn_cache = SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL,
            )
            logger.info("Embedding model: %s (sentence-transformers)", EMBEDDING_MODEL)
        except Exception:  # noqa: BLE001
            _embedding_fn_cache = None
            logger.info("Embedding model: default ONNX (sentence-transformers not available)")

        _embedding_initialized = True

    return _embedding_fn_cache


def pre_warm_embedding() -> None:
    """Pre-load embedding model at startup to avoid cold-start blocking.

    Call this from the main entry point *before* starting the event loop
    so the first real tool call doesn't block 2-5 seconds.
    """
    logger.info("Pre-warming embedding model...")
    get_embedding_fn()
    logger.info("Embedding model ready.")

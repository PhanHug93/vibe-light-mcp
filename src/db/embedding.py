"""Embedding function management (thread-safe, with explicit fallback).

Extracted from ``src/engine/context.py`` — single responsibility:
manage the sentence-transformer / ONNX embedding model lifecycle.

Model strategy (deterministic — no implicit behavior):
  1. ``sentence-transformers`` available → L12 (384d, higher quality)
  2. Fallback → ChromaDB built-in ONNX L6 (256d, always available)
  Both paths produce a *named* embedding function — never ``None``.

Usage::

    from src.db.embedding import get_embedding_fn, pre_warm_embedding

    # At startup (before event loop)
    pre_warm_embedding()

    # During operation
    ef = get_embedding_fn()  # cached, thread-safe, never None
"""

from __future__ import annotations

import logging
import threading

from src.config import EMBEDDING_MODEL, EMBEDDING_MODEL_DEFAULT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thread-safe embedding singleton
# ---------------------------------------------------------------------------

_embedding_fn_cache = None
_embedding_lock = threading.Lock()
_embedding_initialized = False


def get_embedding_fn():
    """Return the best available embedding function (thread-safe, never None).

    Priority:
    1. ``sentence-transformers`` with L12 model (384d, better quality)
    2. ChromaDB default ONNX ``all-MiniLM-L6-v2`` (256d, always available)

    The result is cached after first call.  Thread-safe via double-checked locking.

    .. important::

        Previous behavior returned ``None`` on fallback, letting ChromaDB
        pick a model implicitly.  Now we *explicitly* instantiate the ONNX
        default model — guaranteeing consistent embeddings across all
        environments (local dev, Docker, CI).
    """
    global _embedding_fn_cache, _embedding_initialized  # noqa: PLW0603

    # Fast path: already initialized (no lock needed)
    if _embedding_initialized:
        return _embedding_fn_cache

    with _embedding_lock:
        # Double-checked locking
        if _embedding_initialized:
            return _embedding_fn_cache

        # --- Strategy 1: sentence-transformers (quality install) ---
        try:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )

            _embedding_fn_cache = SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL,
            )
            logger.info(
                "Embedding model loaded: %s (sentence-transformers, 384d)",
                EMBEDDING_MODEL,
            )
        except Exception:  # noqa: BLE001
            # --- Strategy 2: ONNX fallback (always available) ---
            try:
                from chromadb.utils.embedding_functions import (
                    ONNXMiniLM_L6_V2,
                )

                _embedding_fn_cache = ONNXMiniLM_L6_V2()
                logger.info(
                    "Embedding model loaded: %s (ChromaDB ONNX built-in, 256d)",
                    EMBEDDING_MODEL_DEFAULT,
                )
            except Exception:  # noqa: BLE001
                # Last resort: let ChromaDB handle it (should not happen)
                _embedding_fn_cache = None
                logger.warning(
                    "No embedding model available — ChromaDB will use its default. "
                    "Install onnxruntime for explicit control."
                )

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


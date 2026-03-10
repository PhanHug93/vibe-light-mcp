"""
Context Engine — Local RAG via ChromaDB.

Provides standalone functions for anti-context-overflow:
  - ``compress_and_store``  — chunk + embed text into persistent storage.
  - ``query_memory``        — semantic search over stored chunks.

Architecture: Pure database logic — no MCP dependency.
``main.py`` imports these functions and wraps them with ``@mcp.tool()``.

Usage::

    from context_engine import compress_and_store, query_memory
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import chromadb
from chromadb.api.models.Collection import Collection

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ChromaDB initialisation (LAZY — only loads ONNX model on first call)
# ---------------------------------------------------------------------------

_DB_PATH: str = str(Path(__file__).resolve().parent / ".chroma_db")
_COLLECTION_NAME: str = "mcp_memory"

_client: chromadb.ClientAPI | None = None
_collection: Collection | None = None


def _get_collection() -> Collection:
    """Lazy-init ChromaDB client and collection on first access."""
    global _client, _collection  # noqa: PLW0603
    if _collection is None:
        logger.info("Initialising ChromaDB  db=%s ...", _DB_PATH)
        _client = chromadb.PersistentClient(path=_DB_PATH)
        _collection = _client.get_or_create_collection(name=_COLLECTION_NAME)
        logger.info("ContextEngine ready  collection=%s", _COLLECTION_NAME)
    return _collection

# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

_CHUNK_SIZE: int = 1000  # characters per chunk
_CHUNK_OVERLAP: int = 100  # overlap between consecutive chunks


def _chunk_text(
    text: str,
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[str]:
    """Split *text* into overlapping chunks.

    Strategy:
      1. Split on paragraph boundaries (``\\n\\n``).
      2. Accumulate paragraphs until *chunk_size* is reached.
      3. Oversized paragraphs are further split at fixed-window offsets
         with *overlap* to preserve context across boundaries.
    """
    if not text.strip():
        return []

    paragraphs: list[str] = text.split("\n\n")
    chunks: list[str] = []
    current: str = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # Accumulate if it still fits.
        if len(current) + len(para) + 2 <= chunk_size:
            current = f"{current}\n\n{para}" if current else para
        else:
            # Flush accumulated text.
            if current:
                chunks.append(current.strip())
                current = ""

            # Oversized paragraph → fixed-window split.
            if len(para) > chunk_size:
                start = 0
                while start < len(para):
                    end = start + chunk_size
                    chunks.append(para[start:end].strip())
                    start += chunk_size - overlap
            else:
                current = para

    if current.strip():
        chunks.append(current.strip())

    return chunks


# ---------------------------------------------------------------------------
# Core functions (no MCP dependency)
# ---------------------------------------------------------------------------


def compress_and_store(text_data: str, metadata_source: str) -> str:
    """Chunk *text_data*, embed and persist into ChromaDB.

    Args:
        text_data: The text content to compress and store
            (e.g. a log file, source code, documentation).
        metadata_source: A label describing the origin of the text
            (e.g. file path, URL, or free-form description).

    Returns:
        JSON string reporting success / failure and chunk count.
    """
    try:
        chunks = _chunk_text(text_data)
        if not chunks:
            return json.dumps(
                {
                    "status": "skipped",
                    "message": "Input text is empty — nothing to store.",
                },
                ensure_ascii=False,
            )

        batch_id: str = uuid.uuid4().hex[:8]
        ids: list[str] = [f"{batch_id}_{i}" for i in range(len(chunks))]
        metadatas: list[dict[str, str | int]] = [
            {
                "source": metadata_source,
                "batch_id": batch_id,
                "chunk_index": i,
                "total_chunks": len(chunks),
            }
            for i in range(len(chunks))
        ]

        _get_collection().add(documents=chunks, ids=ids, metadatas=metadatas)

        return json.dumps(
            {
                "status": "success",
                "chunks_stored": len(chunks),
                "source": metadata_source,
                "collection": _COLLECTION_NAME,
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("compress_and_store failed")
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )


def query_memory(query: str, n_results: int = 3) -> str:
    """Semantic search over stored chunks in ``mcp_memory``.

    Args:
        query: Natural-language query to search for.
        n_results: Maximum number of results to return (default 3).

    Returns:
        JSON string with the most relevant stored chunks,
        including source and similarity distance.
    """
    try:
        collection = _get_collection()
        total_docs: int = collection.count()
        if total_docs == 0:
            return json.dumps(
                {
                    "status": "no_results",
                    "message": "Memory is empty — store some context first.",
                },
                ensure_ascii=False,
            )

        effective_n: int = min(n_results, total_docs)
        results = collection.query(query_texts=[query], n_results=effective_n)

        documents: list[str] = (
            results["documents"][0] if results["documents"] else []
        )
        metadatas: list[dict] = (
            results["metadatas"][0] if results["metadatas"] else []
        )
        distances: list[float] = (
            results["distances"][0] if results.get("distances") else []
        )

        # Build a human + AI-readable report.
        sections: list[str] = []
        for i, doc in enumerate(documents):
            meta = metadatas[i] if i < len(metadatas) else {}
            dist = distances[i] if i < len(distances) else None
            sections.append(
                f"--- Result {i + 1} ---\n"
                f"Source  : {meta.get('source', 'unknown')}\n"
                f"Distance: {dist}\n"
                f"Chunk # : {meta.get('chunk_index')}\n\n"
                f"{doc}"
            )

        report: str = "\n\n".join(sections)

        return json.dumps(
            {
                "status": "success",
                "total_results": len(documents),
                "results": report,
            },
            indent=2,
            ensure_ascii=False,
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("query_memory failed")
        return json.dumps(
            {"status": "error", "message": str(exc)},
            ensure_ascii=False,
        )

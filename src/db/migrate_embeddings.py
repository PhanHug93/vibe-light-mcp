"""Embedding Migration Engine — Transparent data-preserving migration.

When an existing ChromaDB collection was created with a *different*
embedding function (e.g. the implicit ``default`` from older MCP
versions), ChromaDB raises an error on ``get_or_create_collection``
with the *new* explicit function.

This module detects the mismatch and performs a **safe migration**:

    1. Export all documents + metadata (raw, no embedding function needed)
    2. Backup exported data to JSON on disk
    3. Delete the old collection
    4. Re-create with the correct embedding function
    5. Batch re-import — ChromaDB auto-embeds with the new model

The migration is **idempotent**: once migrated, subsequent calls are
no-ops (detected via successful ``get_or_create_collection``).

Usage::

    from src.db.migrate_embeddings import check_and_migrate

    # At startup — after ChromaDB is reachable
    report = check_and_migrate(client, embedding_fn, ["mcp_global_knowledge"])
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from src.config import (
    CHROMA_DB_PATH,
    CHROMA_DISTANCE_FN,
    L1_PREFIX,
    L2_COLLECTION,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIGRATION_BATCH_SIZE: int = 50
"""Chunks per upsert batch — prevents HTTP timeouts on large collections."""

_BACKUP_DIR_NAME: str = "migration_backups"
"""Subdirectory (under CHROMA_DB_PATH) for pre-migration JSON backups."""

_COLLECTION_METADATA: dict = {"hnsw:space": CHROMA_DISTANCE_FN}
"""Metadata applied to every re-created collection."""


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


def _backup_collection_data(
    collection_name: str,
    ids: list[str],
    documents: list[str],
    metadatas: list[dict],
) -> Path | None:
    """Write collection data to a JSON file before migration.

    Returns the backup path, or ``None`` if backup failed (non-fatal).
    """
    backup_dir = CHROMA_DB_PATH / _BACKUP_DIR_NAME
    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"{collection_name}_{timestamp}.json"

        backup_data = {
            "collection_name": collection_name,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "total_chunks": len(ids),
            "ids": ids,
            "documents": documents,
            "metadatas": metadatas,
        }
        backup_path.write_text(
            json.dumps(backup_data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        size_kb = backup_path.stat().st_size / 1024
        logger.info(
            "Migration backup saved: %s (%.1f KB, %d chunks)",
            backup_path,
            size_kb,
            len(ids),
        )
        return backup_path
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Failed to save migration backup for %s: %s (continuing anyway)",
            collection_name,
            exc,
        )
        return None


# ---------------------------------------------------------------------------
# Single collection migration
# ---------------------------------------------------------------------------


def _migrate_one_collection(
    client: chromadb.HttpClient,
    collection_name: str,
    embedding_fn,
) -> dict:
    """Migrate a single collection to use *embedding_fn*.

    Returns a report dict with keys: ``name``, ``status``, ``chunks``,
    ``elapsed_s``, and optionally ``backup_path`` / ``error``.
    """
    start = time.monotonic()
    report: dict = {"name": collection_name, "status": "unknown", "chunks": 0}

    # ── Step 1: Export raw data (no embedding function) ──────────────
    try:
        old_col = client.get_collection(name=collection_name)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "skipped"
        report["reason"] = f"Collection not found: {exc}"
        return report

    count = old_col.count()
    if count == 0:
        # Empty collection — just delete and recreate
        try:
            client.delete_collection(name=collection_name)
            client.get_or_create_collection(
                name=collection_name,
                embedding_function=embedding_fn,
                metadata=_COLLECTION_METADATA,
            )
        except Exception as exc:  # noqa: BLE001
            report["status"] = "error"
            report["error"] = f"Failed to recreate empty collection: {exc}"
            return report
        report["status"] = "migrated"
        report["chunks"] = 0
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        return report

    logger.info(
        "Exporting %d chunks from '%s' for migration...",
        count,
        collection_name,
    )

    try:
        raw = old_col.get(include=["documents", "metadatas"])
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"Failed to export data: {exc}"
        return report

    ids = raw["ids"]
    documents = raw["documents"] or []
    metadatas = raw["metadatas"] or []

    if not ids:
        report["status"] = "skipped"
        report["reason"] = "No data to migrate"
        return report

    # ── Step 2: Backup to JSON ───────────────────────────────────────
    backup_path = _backup_collection_data(collection_name, ids, documents, metadatas)
    if backup_path:
        report["backup_path"] = str(backup_path)

    # ── Step 3: Delete old collection ────────────────────────────────
    try:
        client.delete_collection(name=collection_name)
        logger.info("Deleted old collection '%s'", collection_name)
    except Exception as exc:  # noqa: BLE001
        report["status"] = "error"
        report["error"] = f"Failed to delete old collection: {exc}"
        return report

    # ── Step 4: Recreate with new embedding function ─────────────────
    try:
        new_col = client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata=_COLLECTION_METADATA,
        )
    except Exception as exc:  # noqa: BLE001
        # CRITICAL: collection deleted but recreation failed
        # Attempt to restore from backup
        report["status"] = "critical_error"
        report["error"] = (
            f"Failed to recreate collection: {exc}. Data backed up at: {backup_path}"
        )
        logger.error(
            "CRITICAL: Collection '%s' deleted but recreation failed: %s. "
            "Restore from backup: %s",
            collection_name,
            exc,
            backup_path,
        )
        return report

    # ── Step 5: Re-import in batches ─────────────────────────────────
    total_imported = 0
    try:
        for batch_start in range(0, len(ids), _MIGRATION_BATCH_SIZE):
            batch_end = min(batch_start + _MIGRATION_BATCH_SIZE, len(ids))
            batch_ids = ids[batch_start:batch_end]
            batch_docs = documents[batch_start:batch_end]
            batch_metas = metadatas[batch_start:batch_end]

            # Filter out entries with empty or None documents
            valid_entries = [
                (i, d, m)
                for i, d, m in zip(batch_ids, batch_docs, batch_metas)
                if d  # skip empty/None documents
            ]
            if valid_entries:
                v_ids, v_docs, v_metas = zip(*valid_entries)
                new_col.upsert(
                    ids=list(v_ids),
                    documents=list(v_docs),
                    metadatas=list(v_metas),
                )
                total_imported += len(v_ids)

        logger.info(
            "Re-imported %d/%d chunks into '%s' with new embedding",
            total_imported,
            len(ids),
            collection_name,
        )
    except Exception as exc:  # noqa: BLE001
        report["status"] = "partial_error"
        report["error"] = f"Import partially failed at chunk {total_imported}: {exc}"
        report["chunks"] = total_imported
        report["elapsed_s"] = round(time.monotonic() - start, 2)
        return report

    report["status"] = "migrated"
    report["chunks"] = total_imported
    report["elapsed_s"] = round(time.monotonic() - start, 2)
    return report


# ---------------------------------------------------------------------------
# Detection: does a collection need migration?
# ---------------------------------------------------------------------------


def _needs_migration(
    client: chromadb.HttpClient,
    collection_name: str,
    embedding_fn,
) -> bool:
    """Return True if *collection_name* exists but rejects *embedding_fn*.

    Heuristic: try ``get_or_create_collection`` with the target EF.
    If it succeeds, no migration needed.  If it raises (embedding
    mismatch), migration IS needed.
    """
    try:
        # Check if collection exists at all
        existing_names = [
            c.name if hasattr(c, "name") else str(c) for c in client.list_collections()
        ]
        if collection_name not in existing_names:
            return False  # Will be created fresh — no migration

        # Try opening with the target embedding function
        client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_fn,
            metadata=_COLLECTION_METADATA,
        )
        return False  # Success — already compatible
    except Exception:  # noqa: BLE001
        return True  # Mismatch — needs migration


# ---------------------------------------------------------------------------
# Public API: check and migrate all relevant collections
# ---------------------------------------------------------------------------


def check_and_migrate(
    client: chromadb.HttpClient,
    embedding_fn,
    collection_names: list[str] | None = None,
) -> dict:
    """Check and migrate collections whose embedding function mismatches.

    If *collection_names* is ``None``, auto-discovers all L1 + L2
    collections from the ChromaDB server.

    Args:
        client: Live ChromaDB HTTP client.
        embedding_fn: The target embedding function (e.g. ONNXMiniLM_L6_V2).
        collection_names: Explicit list of collections to check.
            If None, auto-discovers L1 (``mcp_local_*``) and L2.

    Returns:
        Report dict with ``migrated``, ``skipped``, ``errors`` lists.
    """
    overall_start = time.monotonic()

    if embedding_fn is None:
        logger.warning("No embedding function provided — skipping migration check.")
        return {
            "status": "skipped",
            "reason": "No embedding function available",
        }

    # Auto-discover collections if not specified
    if collection_names is None:
        try:
            all_collections = client.list_collections()
            collection_names = []
            for col in all_collections:
                name = col.name if hasattr(col, "name") else str(col)
                if name == L2_COLLECTION or name.startswith(L1_PREFIX):
                    collection_names.append(name)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to list collections for migration check: %s", exc)
            return {"status": "error", "error": str(exc)}

    if not collection_names:
        logger.info("No L1/L2 collections found — nothing to migrate.")
        return {"status": "no_collections", "message": "No collections to check."}

    migrated: list[dict] = []
    skipped: list[str] = []
    errors: list[dict] = []

    for name in collection_names:
        if _needs_migration(client, name, embedding_fn):
            tier = "L2" if name == L2_COLLECTION else "L1"
            logger.info(
                "⚡ Migration needed for %s collection '%s' — starting...",
                tier,
                name,
            )
            report = _migrate_one_collection(client, name, embedding_fn)
            if report["status"] == "migrated":
                migrated.append(report)
                logger.info(
                    "✅ Migrated '%s': %d chunks in %.1fs",
                    name,
                    report["chunks"],
                    report["elapsed_s"],
                )
            else:
                errors.append(report)
                logger.error("❌ Migration failed for '%s': %s", name, report)
        else:
            skipped.append(name)

    total_elapsed = round(time.monotonic() - overall_start, 2)

    summary = {
        "status": "completed",
        "total_elapsed_s": total_elapsed,
        "migrated": migrated,
        "skipped": skipped,
        "errors": errors,
        "summary": (
            f"Migrated {len(migrated)} collection(s), "
            f"skipped {len(skipped)} (already compatible), "
            f"{len(errors)} error(s)."
        ),
    }

    if migrated:
        total_chunks = sum(r["chunks"] for r in migrated)
        logger.info(
            "🎉 Embedding migration complete: %d collection(s), "
            "%d total chunks in %.1fs",
            len(migrated),
            total_chunks,
            total_elapsed,
        )
    else:
        logger.info("No migration needed — all collections are compatible.")

    return summary

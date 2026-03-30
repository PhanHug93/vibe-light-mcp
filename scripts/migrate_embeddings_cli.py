#!/usr/bin/env python3
"""CLI tool: Migrate ChromaDB collections to the correct embedding function.

Standalone script — does NOT require the MCP server to be running.
Only needs ChromaDB HTTP server to be accessible.

Usage::

    # Preview what would be migrated (safe, read-only)
    python scripts/migrate_embeddings_cli.py --dry-run

    # Execute migration
    python scripts/migrate_embeddings_cli.py

    # Custom ChromaDB address
    python scripts/migrate_embeddings_cli.py --host localhost --port 8888

Environment variables (alternative to CLI args)::

    MCP_CHROMA_HOST=localhost MCP_CHROMA_PORT=8888 python scripts/migrate_embeddings_cli.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Ensure project root is on sys.path
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

import logging  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("migrate_cli")


def main() -> None:
    """Run embedding migration from CLI."""
    parser = argparse.ArgumentParser(
        description="Migrate ChromaDB collections to explicit embedding function.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_CHROMA_HOST", "localhost"),
        help="ChromaDB host (default: localhost, env: MCP_CHROMA_HOST)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_CHROMA_PORT", "8888")),
        help="ChromaDB port (default: 8888, env: MCP_CHROMA_PORT)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only — show which collections need migration without changing anything.",
    )
    args = parser.parse_args()

    # ── Connect to ChromaDB ──────────────────────────────────────────
    import chromadb

    print(f"\n🔌 Connecting to ChromaDB at {args.host}:{args.port}...")
    try:
        client = chromadb.HttpClient(host=args.host, port=args.port)
        client.heartbeat()
        print("   ✅ Connected\n")
    except Exception as exc:
        print(f"   ❌ Failed: {exc}")
        print("\n   Start ChromaDB first:")
        print(f"     chroma run --path ~/.mcp_global_db --port {args.port}")
        sys.exit(1)

    # ── Load embedding function ──────────────────────────────────────
    from src.db.embedding import get_embedding_fn

    ef = get_embedding_fn()
    if ef is None:
        print("❌ No embedding function available.")
        print("   Install: pip install onnxruntime")
        sys.exit(1)

    ef_name = getattr(ef, "_model_name", type(ef).__name__)
    print(f"📦 Embedding function: {ef_name}\n")

    # ── List collections ─────────────────────────────────────────────
    from src.config import L1_PREFIX, L2_COLLECTION
    from src.db.migrate_embeddings import _needs_migration

    all_collections = client.list_collections()
    relevant = []
    for col in all_collections:
        name = col.name if hasattr(col, "name") else str(col)
        if name == L2_COLLECTION or name.startswith(L1_PREFIX):
            relevant.append(name)

    if not relevant:
        print("ℹ️  No L1/L2 collections found. Nothing to do.")
        sys.exit(0)

    print(f"📋 Found {len(relevant)} collection(s):")
    needs_migration = []
    for name in relevant:
        tier = "L2" if name == L2_COLLECTION else "L1"
        try:
            col = client.get_collection(name=name)
            count = col.count()
        except Exception:
            count = "?"

        need = _needs_migration(client, name, ef)
        status = "⚠️  NEEDS MIGRATION" if need else "✅ compatible"
        print(f"   [{tier}] {name} ({count} chunks) — {status}")

        if need:
            needs_migration.append(name)

    print()

    if not needs_migration:
        print("✅ All collections are already compatible. No migration needed.")
        sys.exit(0)

    # ── Dry run ──────────────────────────────────────────────────────
    if args.dry_run:
        print(f"🔍 DRY RUN: {len(needs_migration)} collection(s) would be migrated:")
        for name in needs_migration:
            print(f"   → {name}")
        print("\nRun without --dry-run to execute migration.")
        sys.exit(0)

    # ── Execute migration ────────────────────────────────────────────
    print(f"🚀 Migrating {len(needs_migration)} collection(s)...\n")

    from src.db.migrate_embeddings import check_and_migrate

    report = check_and_migrate(client, ef, needs_migration)

    print(f"\n{'=' * 60}")
    print("📊 Migration Report")
    print(f"{'=' * 60}")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()

    if report.get("errors"):
        print("⚠️  Some migrations failed — check errors above.")
        sys.exit(1)
    else:
        print("🎉 Migration completed successfully!")


if __name__ == "__main__":
    main()

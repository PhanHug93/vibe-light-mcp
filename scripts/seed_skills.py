#!/usr/bin/env python3
"""Seed L2 ChromaDB with SKILL.md files from agent-skills-standard repos.

Multi-threaded import: parses all SKILL.md files from a cloned repo,
groups by category, and upserts into ChromaDB L2 collection in parallel.

Usage::

    # From MCP server root (so src/ is importable)
    python3 scripts/seed_skills.py /path/to/cloned/skills

    # Or via the shell wrapper:
    ./scripts/import_skills.sh
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure MCP server src/ is importable
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import CHROMA_HOST, CHROMA_PORT, CHROMA_DISTANCE_FN  # noqa: E402
from src.utils.text_splitter import recursive_text_split  # noqa: E402

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed_skills")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
L2_COLLECTION = "mcp_global_knowledge"
MAX_WORKERS = 5

# Auto-mapping: folder name → tech_stack key
# Falls back to folder name with hyphens replaced by underscores
CATEGORY_MAP: dict[str, str] = {
    "android": "android_kotlin",
    "flutter": "flutter_dart",
    "ios": "ios_swift",
    "react-native": "react_native",
    "spring-boot": "spring_boot",
    "quality-engineering": "quality_engineering",
    "vue": "vue_js",
}


# ---------------------------------------------------------------------------
# SKILL.md Parser
# ---------------------------------------------------------------------------


def parse_skill_md(filepath: Path) -> dict[str, str]:
    """Parse a SKILL.md file — extract YAML frontmatter + markdown body.

    Returns dict with keys: name, description, content, source.
    """
    text = filepath.read_text(encoding="utf-8", errors="replace")

    # Extract YAML frontmatter (between --- delimiters)
    name = filepath.parent.name  # fallback: folder name
    description = ""

    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if fm_match:
        fm_block = fm_match.group(1)
        # Simple YAML parsing (avoid dependency on PyYAML)
        for line in fm_block.split("\n"):
            line = line.strip()
            if line.startswith("name:"):
                name = line[5:].strip().strip("\"'")
            elif line.startswith("description:"):
                description = line[12:].strip().strip("\"'")
        # Remove frontmatter from body
        body = text[fm_match.end() :]
    else:
        body = text

    return {
        "name": name,
        "description": description,
        "content": body.strip(),
        "source": str(filepath),
    }


def resolve_tech_stack(category_folder: str) -> str:
    """Map a category folder name to a tech_stack key."""
    if category_folder in CATEGORY_MAP:
        return CATEGORY_MAP[category_folder]
    return category_folder.replace("-", "_")


# ---------------------------------------------------------------------------
# Skill Discovery
# ---------------------------------------------------------------------------


def discover_skills(skills_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Walk skills_dir and group SKILL.md files by category.

    Expected structure: skills/{category}/{skill-name}/SKILL.md

    Returns: {tech_stack_key: [parsed_skill, ...]}
    """
    grouped: dict[str, list[dict[str, str]]] = {}

    if not skills_dir.is_dir():
        logger.error("Skills directory not found: %s", skills_dir)
        return grouped

    for skill_file in sorted(skills_dir.rglob("SKILL.md")):
        # Expected: skills_dir / category / skill-name / SKILL.md
        rel = skill_file.relative_to(skills_dir)
        parts = rel.parts  # (category, skill-name, SKILL.md)

        if len(parts) < 3:
            logger.warning("Skipping unexpected path: %s", rel)
            continue

        category = parts[0]
        tech_stack = resolve_tech_stack(category)

        parsed = parse_skill_md(skill_file)
        # Override source with relative path
        parsed["source"] = f"skills/{'/'.join(parts[:-1])}/SKILL.md"
        parsed["category"] = category

        grouped.setdefault(tech_stack, []).append(parsed)

    return grouped


# ---------------------------------------------------------------------------
# ChromaDB Import (per category — runs in thread)
# ---------------------------------------------------------------------------


def import_category(
    tech_stack: str,
    skills: list[dict[str, str]],
    collection: Any,
) -> dict[str, Any]:
    """Import all skills for one category into ChromaDB L2.

    Strategy: concatenate all skills into one large document per category,
    then chunk and upsert. This keeps related skills close in vector space.
    """
    start = time.monotonic()

    # Build merged document
    sections: list[str] = []
    for skill in skills:
        header = f"## {skill['name']}"
        if skill["description"]:
            header += f"\n> {skill['description']}"
        sections.append(f"{header}\n\n{skill['content']}")

    merged_doc = "\n\n---\n\n".join(sections)

    # Chunk
    chunks = recursive_text_split(merged_doc)
    if not chunks:
        return {
            "tech_stack": tech_stack,
            "skills": len(skills),
            "chunks": 0,
            "status": "skipped",
            "time_ms": 0,
        }

    # Build IDs and metadata (same logic as context.py _sync_store)
    metadata_source = f"agent-skills-standard/{tech_stack}"
    batch_id = hashlib.md5(f"{metadata_source}:L2:global".encode()).hexdigest()[:8]
    timestamp = datetime.now(timezone.utc).isoformat()

    ids = [
        hashlib.sha256(f"{metadata_source}:{chunk}".encode()).hexdigest()[:16] + f"_{i}"
        for i, chunk in enumerate(chunks)
    ]
    metadatas = [
        {
            "source": metadata_source,
            "tech_stack": tech_stack,
            "tier": "L2",
            "workspace_id": "global",
            "timestamp": timestamp,
            "batch_id": batch_id,
            "chunk_index": i,
            "total_chunks": len(chunks),
        }
        for i in range(len(chunks))
    ]

    # Upsert (idempotent — same content+source → overwrite)
    collection.upsert(documents=chunks, ids=ids, metadatas=metadatas)

    elapsed_ms = int((time.monotonic() - start) * 1000)
    skill_names = [s["name"] for s in skills]

    logger.info(
        "✅ %-20s  %2d skills  %3d chunks  %dms",
        tech_stack,
        len(skills),
        len(chunks),
        elapsed_ms,
    )

    return {
        "tech_stack": tech_stack,
        "skills": len(skills),
        "chunks": len(chunks),
        "skill_names": skill_names,
        "status": "success",
        "time_ms": elapsed_ms,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import SKILL.md files into ChromaDB L2 (multi-threaded)."
    )
    parser.add_argument(
        "skills_dir",
        type=Path,
        help="Path to the 'skills/' directory from a cloned repo.",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_CHROMA_HOST", CHROMA_HOST),
        help=f"ChromaDB host (default: {CHROMA_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("MCP_CHROMA_PORT", str(CHROMA_PORT))),
        help=f"ChromaDB port (default: {CHROMA_PORT})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=MAX_WORKERS,
        help=f"Number of parallel threads (default: {MAX_WORKERS})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without writing to ChromaDB.",
    )
    args = parser.parse_args()

    # ── Discover skills ──────────────────────────────────────────
    logger.info("📂 Scanning: %s", args.skills_dir)
    grouped = discover_skills(args.skills_dir)

    if not grouped:
        logger.error("❌ No SKILL.md files found!")
        sys.exit(1)

    total_skills = sum(len(v) for v in grouped.values())
    logger.info(
        "📊 Found %d skills across %d categories",
        total_skills,
        len(grouped),
    )

    if args.dry_run:
        print("\n🔍 Dry-run results:")
        for tech_stack, skills in sorted(grouped.items()):
            names = [s["name"] for s in skills]
            print(f"  {tech_stack}: {len(skills)} skills — {', '.join(names)}")
        print(f"\n  Total: {total_skills} skills, {len(grouped)} categories")
        return

    # ── Connect to ChromaDB ─────────────────────────────────────
    try:
        import chromadb
    except ImportError:
        logger.error("❌ chromadb not installed. Run: pip install chromadb")
        sys.exit(1)

    logger.info("🔌 Connecting to ChromaDB at %s:%d...", args.host, args.port)
    try:
        client = chromadb.HttpClient(host=args.host, port=args.port)
        client.heartbeat()
    except Exception as exc:
        logger.error("❌ ChromaDB connection failed: %s", exc)
        sys.exit(1)

    # Get or create L2 collection with embedding function
    from src.db.embedding import get_embedding_fn

    ef = get_embedding_fn()
    collection = client.get_or_create_collection(
        name=L2_COLLECTION,
        embedding_function=ef,
        metadata={"hnsw:space": CHROMA_DISTANCE_FN},
    )
    l2_before = collection.count()
    logger.info("📦 L2 collection '%s' has %d chunks", L2_COLLECTION, l2_before)

    # ── Multi-threaded import ───────────────────────────────────
    logger.info("🚀 Starting import with %d threads...\n", args.workers)
    start_total = time.monotonic()
    results: list[dict[str, Any]] = []

    with ThreadPoolExecutor(
        max_workers=args.workers,
        thread_name_prefix="import",
    ) as executor:
        futures = {
            executor.submit(import_category, ts, skills, collection): ts
            for ts, skills in grouped.items()
        }

        for future in as_completed(futures):
            ts = futures[future]
            try:
                result = future.result(timeout=120)
                results.append(result)
            except Exception as exc:
                logger.error("❌ %s failed: %s", ts, exc)
                results.append(
                    {
                        "tech_stack": ts,
                        "status": "error",
                        "error": str(exc),
                    }
                )

    # ── Summary ─────────────────────────────────────────────────
    elapsed_total = time.monotonic() - start_total
    l2_after = collection.count()
    total_chunks = sum(r.get("chunks", 0) for r in results)
    success_count = sum(1 for r in results if r.get("status") == "success")
    error_count = sum(1 for r in results if r.get("status") == "error")

    print("\n" + "=" * 60)
    print("📊 IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Categories : {len(grouped)} ({success_count} ✅, {error_count} ❌)")
    print(f"  Skills     : {total_skills}")
    print(f"  Chunks     : {total_chunks} new")
    print(f"  L2 before  : {l2_before}")
    print(f"  L2 after   : {l2_after}")
    print(f"  Time       : {elapsed_total:.1f}s")
    print(f"  Workers    : {args.workers}")
    print("=" * 60)

    # Write report JSON
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_skills": total_skills,
        "total_categories": len(grouped),
        "total_chunks": total_chunks,
        "l2_before": l2_before,
        "l2_after": l2_after,
        "elapsed_seconds": round(elapsed_total, 1),
        "results": results,
    }
    report_path = _SCRIPT_DIR / "last_import_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("📄 Report saved: %s", report_path)


if __name__ == "__main__":
    main()

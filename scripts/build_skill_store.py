#!/usr/bin/env python3
"""Build the SQLite local skill store from audited YAML digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import SKILL_REGISTRY_DIR, SKILL_STORE_PATH  # noqa: E402
from src.engine.skill_store import SKILL_STORE_SCHEMA  # noqa: E402
from src.engine.skills import (  # noqa: E402
    _estimate_tokens,
    _load_source_text,
    render_skill_digest,
)

BUILDER_VERSION = "0.0.1"
CANDIDATE_SCHEMA = "local-skill-candidate/v0.0.1"


def _load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"YAML must be a mapping: {path}")
    return data


def _require_fts5(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("create virtual table temp._fts5_check using fts5(value)")
        conn.execute("drop table temp._fts5_check")
    except sqlite3.Error as exc:
        raise RuntimeError("SQLite FTS5 is required for local skill store builds") from exc


def _json_list(values: Any) -> str:
    return json.dumps([str(value) for value in values or []], ensure_ascii=False)


def _render_full_content(digest_data: dict[str, Any], rendered_digest: str) -> str:
    sections = [rendered_digest.strip()]
    for source in digest_data.get("full_content_sources", []):
        loaded = _load_source_text(str(source))
        if not loaded:
            continue
        source_name, text = loaded
        sections.append(f"## Full Source: {source_name}\n\n{text}")
    return "\n\n---\n\n".join(sections).strip() + "\n"


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        create table metadata(
          key text primary key,
          value text not null
        );

        create table skills(
          id text primary key,
          version text not null,
          status text not null,
          digest_path text not null,
          digest_hash text not null,
          rendered_digest text not null,
          full_content text,
          aliases_json text not null,
          facets_json text not null,
          platforms_json text not null,
          languages_json text not null,
          source_json text not null,
          token_estimate integer not null
        );

        create virtual table skill_fts using fts5(
          skill_id unindexed,
          name,
          description,
          aliases,
          facets,
          body
        );
        """
    )


def _insert_metadata(conn: sqlite3.Connection, registry_dir: Path) -> None:
    metadata = {
        "schema_version": SKILL_STORE_SCHEMA,
        "builder_version": BUILDER_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_registry": str((registry_dir / "registry.yaml").resolve()),
        "vector_enabled": "false",
    }
    conn.executemany(
        "insert into metadata(key, value) values(?, ?)",
        sorted(metadata.items()),
    )


def _skill_description(digest_data: dict[str, Any]) -> str:
    contract = digest_data.get("agent_contract") or {}
    return str(contract.get("primary_instruction", "")).strip()


def _insert_skill(
    conn: sqlite3.Connection,
    *,
    registry_dir: Path,
    entry: dict[str, Any],
) -> None:
    skill_id = str(entry["id"])
    digest_path = registry_dir / str(entry["digest_path"])
    digest_data = _load_yaml(digest_path)
    rendered_digest = render_skill_digest(digest_data)
    digest_hash = f"sha256:{hashlib.sha256(rendered_digest.encode('utf-8')).hexdigest()}"
    full_content = _render_full_content(digest_data, rendered_digest)
    applies_to = digest_data.get("applies_to") or {}
    facets = entry.get("facets") or applies_to.get("facets") or []
    aliases = entry.get("aliases") or []
    platforms = entry.get("platforms") or []
    languages = entry.get("languages") or []
    description = _skill_description(digest_data)
    source = {
        "registry": str((registry_dir / "registry.yaml").resolve()),
        "digest": str(digest_path.resolve()),
        "source_pack": entry.get("source_pack", {}),
    }

    conn.execute(
        """
        insert into skills(
          id, version, status, digest_path, digest_hash, rendered_digest,
          full_content, aliases_json, facets_json, platforms_json, languages_json,
          source_json, token_estimate
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            skill_id,
            str(entry.get("version", digest_data.get("version", "unknown"))),
            str(entry.get("status", "unknown")),
            str(Path(entry["digest_path"])),
            digest_hash,
            rendered_digest,
            full_content,
            _json_list(aliases),
            _json_list(facets),
            _json_list(platforms),
            _json_list(languages),
            json.dumps(source, ensure_ascii=False, sort_keys=True),
            _estimate_tokens(rendered_digest),
        ),
    )
    conn.execute(
        "insert into skill_fts(skill_id, name, description, aliases, facets, body) "
        "values (?, ?, ?, ?, ?, ?)",
        (
            skill_id,
            skill_id,
            description,
            " ".join(str(value) for value in aliases),
            " ".join(str(value) for value in [*facets, *platforms, *languages]),
            rendered_digest,
        ),
    )


def _load_candidate_manifests(registry_dir: Path) -> list[dict[str, Any]]:
    candidates_dir = registry_dir / "candidates"
    if not candidates_dir.is_dir():
        return []
    manifests: list[dict[str, Any]] = []
    for path in sorted(candidates_dir.rglob("*.yaml")):
        data = _load_yaml(path)
        if data.get("schema_version") != CANDIDATE_SCHEMA:
            raise ValueError(f"Unsupported candidate schema: {path}")
        manifests.append(data)
    return manifests


def _insert_candidate(conn: sqlite3.Connection, *, manifest: dict[str, Any]) -> None:
    candidate_id = str(manifest["id"])
    status = str(manifest.get("status", "candidate"))
    if status not in {"candidate", "review"}:
        raise ValueError(f"Invalid candidate status for {candidate_id}: {status}")
    content = manifest.get("content") or {}
    text = str(content.get("text", "")).strip()
    if not text:
        raise ValueError(f"Candidate content is empty: {candidate_id}")
    digest_hash = f"sha256:{content.get('sha256') or hashlib.sha256(text.encode('utf-8')).hexdigest()}"
    source = dict(manifest.get("source") or {})
    source["license"] = manifest.get("license", {})
    source["risk"] = manifest.get("risk", {})
    source["source_tier"] = manifest.get("source_tier", "")
    facets = manifest.get("facets") or []
    aliases = manifest.get("aliases") or []
    platforms = manifest.get("platforms") or []
    languages = manifest.get("languages") or []

    conn.execute(
        """
        insert into skills(
          id, version, status, digest_path, digest_hash, rendered_digest,
          full_content, aliases_json, facets_json, platforms_json, languages_json,
          source_json, token_estimate
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            candidate_id,
            "0.0.0-candidate",
            status,
            str(source.get("path", "")),
            digest_hash,
            text,
            text,
            _json_list(aliases),
            _json_list(facets),
            _json_list(platforms),
            _json_list(languages),
            json.dumps(source, ensure_ascii=False, sort_keys=True),
            _estimate_tokens(text),
        ),
    )
    conn.execute(
        "insert into skill_fts(skill_id, name, description, aliases, facets, body) "
        "values (?, ?, ?, ?, ?, ?)",
        (
            candidate_id,
            str(manifest.get("name", candidate_id)),
            str(manifest.get("description", "")),
            " ".join(str(value) for value in aliases),
            " ".join(str(value) for value in [*facets, *platforms, *languages]),
            text,
        ),
    )


def build_skill_store(registry_dir: Path, output_path: Path) -> dict[str, Any]:
    registry_dir = registry_dir.resolve()
    output_path = output_path.resolve()
    registry = _load_yaml(registry_dir / "registry.yaml")
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise ValueError("Skill registry must contain a skills list.")
    candidates = _load_candidate_manifests(registry_dir)
    seen_ids: set[str] = set()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        dir=str(output_path.parent),
    )
    os.close(fd)
    temp_path = Path(temp_name)
    try:
        with sqlite3.connect(temp_path) as conn:
            _require_fts5(conn)
            _create_schema(conn)
            _insert_metadata(conn, registry_dir)
            for entry in skills:
                if not isinstance(entry, dict):
                    raise ValueError("Skill registry entries must be mappings.")
                skill_id = str(entry.get("id", ""))
                if skill_id in seen_ids:
                    raise ValueError(f"Duplicate skill id: {skill_id}")
                seen_ids.add(skill_id)
                _insert_skill(conn, registry_dir=registry_dir, entry=entry)
            for manifest in candidates:
                candidate_id = str(manifest.get("id", ""))
                if candidate_id in seen_ids:
                    raise ValueError(f"Duplicate skill id: {candidate_id}")
                seen_ids.add(candidate_id)
                _insert_candidate(conn, manifest=manifest)
            conn.commit()
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {
        "output_path": str(output_path),
        "skills": len(skills),
        "candidates": len(candidates),
        "schema_version": SKILL_STORE_SCHEMA,
        "vector_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the local SQLite skill store.")
    parser.add_argument(
        "--registry-dir",
        type=Path,
        default=SKILL_REGISTRY_DIR,
        help="Path to skill_registry directory.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=SKILL_STORE_PATH,
        help="Output SQLite path.",
    )
    args = parser.parse_args()

    result = build_skill_store(args.registry_dir, args.output)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

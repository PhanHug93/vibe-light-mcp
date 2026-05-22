"""SQLite-backed local skill store for audited skill delivery."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SKILL_STORE_SCHEMA = "local-skill-store/v0.0.1"


class SkillStoreUnavailable(RuntimeError):
    """Raised when the SQLite skill store cannot be used safely."""


class SQLiteSkillStore:
    """Read adapter for the generated local skill SQLite store."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise SkillStoreUnavailable(f"Skill store not found: {self.db_path}")
        uri = f"file:{self.db_path}?mode=ro"
        try:
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            raise SkillStoreUnavailable(f"Cannot open skill store: {exc}") from exc
        conn.row_factory = sqlite3.Row
        return conn

    def _load_metadata(self, conn: sqlite3.Connection) -> dict[str, str]:
        try:
            rows = conn.execute("select key, value from metadata").fetchall()
        except sqlite3.Error as exc:
            raise SkillStoreUnavailable(f"Invalid skill store metadata: {exc}") from exc
        metadata = {str(row["key"]): str(row["value"]) for row in rows}
        if metadata.get("schema_version") != SKILL_STORE_SCHEMA:
            raise SkillStoreUnavailable(
                f"Unsupported skill store schema: {metadata.get('schema_version')}"
            )
        return metadata

    @staticmethod
    def _decode_json_list(value: str) -> list[str]:
        data = json.loads(value)
        if not isinstance(data, list):
            raise ValueError("Expected JSON list")
        return [str(item) for item in data]

    @classmethod
    def _row_to_entry(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "version": str(row["version"]),
            "status": str(row["status"]),
            "digest_path": str(row["digest_path"]),
            "aliases": cls._decode_json_list(str(row["aliases_json"])),
            "facets": cls._decode_json_list(str(row["facets_json"])),
            "platforms": cls._decode_json_list(str(row["platforms_json"])),
            "languages": cls._decode_json_list(str(row["languages_json"])),
        }

    @classmethod
    def _row_to_payload_source(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "entry": cls._row_to_entry(row),
            "rendered_digest": str(row["rendered_digest"]),
            "full_content": str(row["full_content"] or ""),
            "digest_hash": str(row["digest_hash"]),
            "source": json.loads(str(row["source_json"])),
        }

    def load_registry(self) -> dict[str, Any]:
        try:
            with self._connect() as conn:
                self._load_metadata(conn)
                rows = conn.execute(
                    "select id, version, status, digest_path, aliases_json, "
                    "facets_json, platforms_json, languages_json "
                    "from skills where status = 'audited' order by id"
                ).fetchall()
        except sqlite3.Error as exc:
            raise SkillStoreUnavailable(f"Cannot read skill store: {exc}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise SkillStoreUnavailable(f"Malformed skill store row: {exc}") from exc

        return {
            "schema_version": SKILL_STORE_SCHEMA,
            "skills": [self._row_to_entry(row) for row in rows],
            "planned_facets": {},
        }

    def load_payload_sources(self, skill_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not skill_ids:
            return {}
        placeholders = ",".join("?" for _ in skill_ids)
        query = (
            "select id, version, status, digest_path, digest_hash, rendered_digest, "
            "full_content, aliases_json, facets_json, platforms_json, languages_json, "
            f"source_json from skills where id in ({placeholders})"
        )
        try:
            with self._connect() as conn:
                self._load_metadata(conn)
                rows = conn.execute(query, skill_ids).fetchall()
        except sqlite3.Error as exc:
            raise SkillStoreUnavailable(f"Cannot read skill payloads: {exc}") from exc
        except (json.JSONDecodeError, ValueError) as exc:
            raise SkillStoreUnavailable(f"Malformed skill payload row: {exc}") from exc
        return {str(row["id"]): self._row_to_payload_source(row) for row in rows}

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        cleaned = query.strip()
        if not cleaned:
            return []
        try:
            with self._connect() as conn:
                self._load_metadata(conn)
                rows = conn.execute(
                    "select skills.id, skills.status, bm25(skill_fts) as score "
                    "from skill_fts join skills on skills.id = skill_fts.skill_id "
                    "where skill_fts match ? "
                    "order by score, skills.id limit ?",
                    (cleaned, limit),
                ).fetchall()
        except sqlite3.Error as exc:
            raise SkillStoreUnavailable(f"Skill FTS search failed: {exc}") from exc
        return [
            {"id": str(row["id"]), "status": str(row["status"]), "score": row["score"]}
            for row in rows
        ]

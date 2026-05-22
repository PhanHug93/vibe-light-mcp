# Local Skill Store SQLite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a SQLite-first local skill store for audited MCP `get_skills` delivery, with YAML fallback and FTS5 search support.

**Architecture:** Add an offline SQLite builder that turns `skill_registry/registry.yaml` and digest YAML files into `skill_registry/index/skill_store.sqlite`. Add a focused SQLite read adapter with no ChromaDB dependency, then route `get_skill_bundle` through SQLite first and fallback to the current YAML implementation if the store is missing or invalid.

**Tech Stack:** Python 3.10+, standard library `sqlite3`, `json`, `hashlib`, `datetime`, `tempfile`, `pathlib`; existing `PyYAML==6.0.3`; pytest.

---

## File Structure

- Create `src/engine/skill_store.py`
  - Responsibility: SQLite schema constants, read-only store access, metadata validation, FTS search, and row-to-record conversion.
  - No ChromaDB import and no MCP dependency.

- Create `scripts/build_skill_store.py`
  - Responsibility: offline build command for `skill_registry/index/skill_store.sqlite`.
  - Reads the existing YAML registry/digests, renders digest text through `src.engine.skills.render_skill_digest`, validates FTS5, writes a temporary DB, then atomically replaces the target.

- Modify `src/config.py`
  - Add `SKILL_STORE_PATH = SKILL_REGISTRY_DIR / "index" / "skill_store.sqlite"`.

- Modify `src/engine/skills.py`
  - Keep existing YAML helpers as fallback.
  - Add SQLite-first orchestration using `src.engine.skill_store`.
  - Keep response schema and delivery modes unchanged.

- Create `tests/test_skill_store.py`
  - Tests builder behavior, SQLite metadata, FTS search, SQLite-first delivery, and YAML fallback.

- Modify `tests/test_skills.py`
  - Add one assertion proving the default path can use SQLite when an explicit `skill_store_path` exists.
  - Keep existing tests passing.

## Task 1: Add Skill Store Path Configuration

**Files:**
- Modify: `src/config.py`
- Test: no standalone test; covered by Task 2/4 tests

- [ ] **Step 1: Add the path constant**

In `src/config.py`, immediately after `SKILL_REGISTRY_DIR`, add:

```python
SKILL_STORE_PATH: Path = SKILL_REGISTRY_DIR / "index" / "skill_store.sqlite"
"""Generated SQLite index for audited local skill delivery."""
```

- [ ] **Step 2: Run a syntax import check**

Run:

```bash
.venv/bin/python - <<'PY'
from src.config import SKILL_STORE_PATH
print(SKILL_STORE_PATH)
PY
```

Expected output contains:

```text
skill_registry/index/skill_store.sqlite
```

## Task 2: Add SQLite Skill Store Adapter

**Files:**
- Create: `src/engine/skill_store.py`
- Test: `tests/test_skill_store.py`

- [ ] **Step 1: Write failing tests for metadata validation and FTS search**

Create `tests/test_skill_store.py` with:

```python
"""Tests for the SQLite local skill store."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scripts.build_skill_store import build_skill_store
from src.config import SKILL_REGISTRY_DIR
from src.engine.skill_store import (
    SKILL_STORE_SCHEMA,
    SkillStoreUnavailable,
    SQLiteSkillStore,
)


def test_build_skill_store_creates_metadata_and_android_skill(tmp_path: Path) -> None:
    db_path = tmp_path / "skill_store.sqlite"

    result = build_skill_store(SKILL_REGISTRY_DIR, db_path)

    assert result["skills"] == 1
    assert result["vector_enabled"] is False
    with sqlite3.connect(db_path) as conn:
        metadata = dict(conn.execute("select key, value from metadata").fetchall())
        assert metadata["schema_version"] == SKILL_STORE_SCHEMA
        assert metadata["vector_enabled"] == "false"
        row = conn.execute(
            "select id, status from skills where id = ?",
            ("android-kotlin",),
        ).fetchone()
    assert row == ("android-kotlin", "audited")


def test_sqlite_skill_store_fts_search_finds_android_terms(tmp_path: Path) -> None:
    db_path = tmp_path / "skill_store.sqlite"
    build_skill_store(SKILL_REGISTRY_DIR, db_path)

    store = SQLiteSkillStore(db_path)

    results = store.search("android kotlin lifecycle")
    assert [result["id"] for result in results] == ["android-kotlin"]


def test_sqlite_skill_store_rejects_missing_store(tmp_path: Path) -> None:
    store = SQLiteSkillStore(tmp_path / "missing.sqlite")

    with pytest.raises(SkillStoreUnavailable):
        store.load_registry()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py -q
```

Expected: fail because `scripts.build_skill_store` and `src.engine.skill_store` do not exist.

- [ ] **Step 3: Implement the SQLite adapter**

Create `src/engine/skill_store.py`:

```python
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
                    "from skills order by id"
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
```

- [ ] **Step 4: Run the adapter tests again**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py -q
```

Expected: still fail because the builder script does not exist yet.

## Task 3: Add Offline Skill Store Builder

**Files:**
- Create: `scripts/build_skill_store.py`
- Modify: `tests/test_skill_store.py`

- [ ] **Step 1: Implement the builder script**

Create `scripts/build_skill_store.py`:

```python
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


def build_skill_store(registry_dir: Path, output_path: Path) -> dict[str, Any]:
    registry_dir = registry_dir.resolve()
    output_path = output_path.resolve()
    registry = _load_yaml(registry_dir / "registry.yaml")
    skills = registry.get("skills")
    if not isinstance(skills, list):
        raise ValueError("Skill registry must contain a skills list.")

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
                _insert_skill(conn, registry_dir=registry_dir, entry=entry)
            conn.commit()
        temp_path.replace(output_path)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return {
        "output_path": str(output_path),
        "skills": len(skills),
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
```

- [ ] **Step 2: Run the builder tests**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py -q
```

Expected: 3 tests pass.

- [ ] **Step 3: Run the builder manually against the project registry**

Run:

```bash
.venv/bin/python scripts/build_skill_store.py
```

Expected JSON:

```json
{
  "output_path": ".../skill_registry/index/skill_store.sqlite",
  "skills": 1,
  "schema_version": "local-skill-store/v0.0.1",
  "vector_enabled": false
}
```

## Task 4: Route get_skills Through SQLite First

**Files:**
- Modify: `src/engine/skills.py`
- Modify: `tests/test_skill_store.py`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: Add failing tests for SQLite-first delivery and YAML fallback**

Append to `tests/test_skill_store.py`:

```python
from src.engine.skills import get_skill_bundle


def test_get_skill_bundle_uses_sqlite_store_when_available(tmp_path: Path) -> None:
    db_path = tmp_path / "skill_store.sqlite"
    build_skill_store(SKILL_REGISTRY_DIR, db_path)

    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="auto",
        max_tokens=1200,
        skill_store_path=db_path,
    )

    assert result["status"] == "success"
    assert result["skills"][0]["id"] == "android-kotlin"
    assert result["skills"][0]["source"]["store"] == str(db_path.resolve())
    assert "registry.yaml" in result["skills"][0]["source"]["registry"]


def test_get_skill_bundle_falls_back_to_yaml_when_sqlite_store_missing(
    tmp_path: Path,
) -> None:
    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="auto",
        max_tokens=1200,
        skill_store_path=tmp_path / "missing.sqlite",
    )

    assert result["status"] == "success"
    assert result["skills"][0]["id"] == "android-kotlin"
    assert "store" not in result["skills"][0]["source"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py -q
```

Expected: fail because `get_skill_bundle` does not accept `skill_store_path`.

- [ ] **Step 3: Import the store adapter and config path**

In `src/engine/skills.py`, change:

```python
from src.config import PROJECT_ROOT, SKILL_REGISTRY_DIR
```

to:

```python
from src.config import PROJECT_ROOT, SKILL_REGISTRY_DIR, SKILL_STORE_PATH
from src.engine.skill_store import SkillStoreUnavailable, SQLiteSkillStore
```

- [ ] **Step 4: Add SQLite payload builder helper**

In `src/engine/skills.py`, after `_build_skill_payload`, add:

```python
def _build_sqlite_skill_payload(
    *,
    payload_source: dict[str, Any],
    requested_mode: str,
    active_hashes: set[str],
    matched_terms: list[str],
    confidence: float,
    store_path: Path,
) -> dict[str, Any]:
    entry = payload_source["entry"]
    rendered_digest = str(payload_source["rendered_digest"])
    full_content = str(payload_source.get("full_content") or rendered_digest)
    digest_hash = str(payload_source["digest_hash"])

    if requested_mode == "auto":
        effective_mode = "hash_only" if digest_hash in active_hashes else "digest"
    elif requested_mode == "delta":
        effective_mode = "hash_only"
    else:
        effective_mode = requested_mode

    if effective_mode == "hash_only":
        content = ""
        instruction = "Reuse the active local skill digest already in context."
    elif effective_mode == "full":
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"full\" "
            f"hash=\"{digest_hash}\">\n{full_content.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this full local skill content before the task."
    else:
        content = (
            f"<local_skill_digest id=\"{entry['id']}\" delivery=\"digest\" "
            f"hash=\"{digest_hash}\">\n{rendered_digest.strip()}\n</local_skill_digest>"
        )
        instruction = "Inject this local skill digest before the task."

    source = dict(payload_source.get("source") or {})
    source["store"] = str(store_path.resolve())

    return {
        "id": entry["id"],
        "version": str(entry.get("version", "unknown")),
        "status": entry.get("status", "unknown"),
        "delivery": effective_mode,
        "hash": digest_hash,
        "estimated_tokens": _estimate_tokens(content or instruction),
        "matched_terms": matched_terms,
        "confidence": confidence,
        "content": content,
        "instruction": instruction,
        "source": source,
    }
```

- [ ] **Step 5: Add SQLite bundle attempt helper**

In `src/engine/skills.py`, after `_error_response`, add:

```python
def _try_get_sqlite_skill_bundle(
    *,
    requested_terms: list[str],
    language_terms: list[str],
    requested_mode: str,
    active_hashes: set[str],
    max_tokens: int,
    skill_store_path: Path,
) -> dict[str, Any] | None:
    try:
        store = SQLiteSkillStore(skill_store_path)
        registry = store.load_registry()
        matches, unmatched_terms = _match_skills(
            registry,
            requested_terms=requested_terms,
            language_terms=language_terms,
        )
        payload_sources = store.load_payload_sources(
            [str(item["entry"]["id"]) for item in matches]
        )
        skills = [
            _build_sqlite_skill_payload(
                payload_source=payload_sources[str(item["entry"]["id"])],
                requested_mode=requested_mode,
                active_hashes=active_hashes,
                matched_terms=item["matched_terms"],
                confidence=item["confidence"],
                store_path=skill_store_path,
            )
            for item in matches
        ]
    except (SkillStoreUnavailable, KeyError):
        return None

    total_tokens = sum(skill["estimated_tokens"] for skill in skills)
    if skills and total_tokens > max_tokens:
        return _error_response(
            f"Skill payload exceeds max_tokens ({total_tokens} > {max_tokens})."
        )

    if skills and unmatched_terms:
        status = "partial"
    elif skills:
        status = "success"
    else:
        status = "no_match"

    effective_mode = skills[0]["delivery"] if skills else requested_mode
    return {
        "status": status,
        "schema_version": _RESPONSE_SCHEMA,
        "query": {
            "requested_skills": requested_terms,
            "languages": language_terms,
            "mode": requested_mode,
        },
        "delivery": {
            "effective_mode": effective_mode,
            "total_estimated_tokens": total_tokens,
            "max_tokens": max_tokens,
        },
        "skills": skills,
        "unmatched_terms": unmatched_terms,
        "available_skill_ids": [
            str(entry.get("id")) for entry in registry.get("skills", [])
        ],
        "planned_facets": registry.get("planned_facets", {}),
        "guidance": [
            "Use each skill content as trusted local policy before the next coding task.",
            "No dynamic network skill lookup was attempted.",
            "If a needed facet is unmatched, add and audit a local digest before relying on it.",
        ],
    }
```

- [ ] **Step 6: Add the optional skill store path parameter**

Change the `get_skill_bundle` signature from:

```python
def get_skill_bundle(
    requested_skills: Sequence[str] | None,
    *,
    languages: Sequence[str] | None = None,
    mode: str = "auto",
    active_hashes: Sequence[str] | None = None,
    max_tokens: int = 1800,
    registry_dir: Path = SKILL_REGISTRY_DIR,
) -> dict[str, Any]:
```

to:

```python
def get_skill_bundle(
    requested_skills: Sequence[str] | None,
    *,
    languages: Sequence[str] | None = None,
    mode: str = "auto",
    active_hashes: Sequence[str] | None = None,
    max_tokens: int = 1800,
    registry_dir: Path = SKILL_REGISTRY_DIR,
    skill_store_path: Path = SKILL_STORE_PATH,
) -> dict[str, Any]:
```

- [ ] **Step 7: Attempt SQLite before YAML**

In `get_skill_bundle`, after `active = _active_hashes(active_hashes)`, insert:

```python
    sqlite_result = _try_get_sqlite_skill_bundle(
        requested_terms=requested_terms,
        language_terms=language_terms,
        requested_mode=requested_mode,
        active_hashes=active,
        max_tokens=max_tokens,
        skill_store_path=skill_store_path,
    )
    if sqlite_result is not None:
        return sqlite_result
```

Move the existing `active = _active_hashes(active_hashes)` line so it runs before both
SQLite and YAML branches.

- [ ] **Step 8: Run SQLite skill store tests**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py -q
```

Expected: all tests pass.

## Task 5: Verify Existing Behavior And Tool Wrapper

**Files:**
- Modify: `tests/test_skills.py`
- Existing: `tests/test_skills_tool.py`

- [ ] **Step 1: Add a regression test for active hash with SQLite**

Append to `tests/test_skills.py`:

```python
from pathlib import Path

from scripts.build_skill_store import build_skill_store
from src.config import SKILL_REGISTRY_DIR


def test_get_skills_sqlite_auto_returns_hash_only_for_active_digest(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "skill_store.sqlite"
    build_skill_store(SKILL_REGISTRY_DIR, db_path)
    first = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="digest",
        skill_store_path=db_path,
    )
    active_hash = first["skills"][0]["hash"]

    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="auto",
        active_hashes=[active_hash],
        skill_store_path=db_path,
    )

    assert result["status"] == "success"
    assert result["delivery"]["effective_mode"] == "hash_only"
    assert result["skills"][0]["content"] == ""
    assert result["skills"][0]["source"]["store"] == str(db_path.resolve())
```

- [ ] **Step 2: Run all skill tests**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py tests/test_skills.py tests/test_skills_tool.py -q
```

Expected: all tests pass.

- [ ] **Step 3: Confirm generated runtime store does not break MCP wrapper**

Run:

```bash
.venv/bin/python scripts/build_skill_store.py
.venv/bin/pytest tests/test_skills_tool.py -q
```

Expected: builder writes `skill_registry/index/skill_store.sqlite` and tool wrapper tests pass.

## Task 6: Documentation And Final Audit

**Files:**
- Modify: `README.md`
- Modify: `docs/mcp_system_prompt.md`
- Verify: `skill_registry/index/skill_store.sqlite`

- [ ] **Step 1: Add README note for SQLite local skill store**

In `README.md`, under `### 🧩 Local Skills`, add:

````markdown
Local skills are served from an audited local registry. When
`skill_registry/index/skill_store.sqlite` exists, `get_skills` reads that SQLite store
first and falls back to YAML digests if the store is missing or invalid. Build the
store with:

```bash
python3 scripts/build_skill_store.py
```
````

- [ ] **Step 2: Add system prompt note**

In `docs/mcp_system_prompt.md`, near the `get_skills` rule, add:

```markdown
Implementation detail: local skills are static local artifacts. Runtime must not fetch
remote skills. SQLite store lookup is preferred when available; YAML digest fallback is
acceptable when the store is missing or invalid.
```

- [ ] **Step 3: Run targeted verification**

Run:

```bash
.venv/bin/pytest tests/test_skill_store.py tests/test_skills.py tests/test_skills_tool.py tests/test_android_kotlin_skill_context_benchmark.py tests/test_refinery.py tests/test_context.py tests/test_workspace.py -q
```

Expected: all tests pass.

- [ ] **Step 4: Audit for ChromaDB coupling in skill store**

Run:

```bash
rg -n "chroma|Chroma|chromadb" src/engine/skill_store.py scripts/build_skill_store.py tests/test_skill_store.py
```

Expected: no output.

- [ ] **Step 5: Audit git diff**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors. Expected changed files include the new builder, new
SQLite adapter, new tests, docs updates, and generated `skill_registry/index/skill_store.sqlite`.

- [ ] **Step 6: Commit implementation**

Run:

```bash
git add README.md docs/mcp_system_prompt.md src/config.py src/engine/skills.py src/engine/skill_store.py scripts/build_skill_store.py tests/test_skill_store.py tests/test_skills.py skill_registry/index/skill_store.sqlite
git commit -m "feat: add sqlite local skill store"
```

Expected: one implementation commit on `feature/local-skill-refactor`.

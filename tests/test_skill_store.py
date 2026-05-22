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
from src.engine.skills import get_skill_bundle


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

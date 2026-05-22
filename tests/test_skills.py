"""Tests for local skill retrieval and delivery."""

from __future__ import annotations

from pathlib import Path

from scripts.build_skill_store import build_skill_store
from src.config import SKILL_REGISTRY_DIR
from src.engine.skills import get_skill_bundle


def test_get_skills_returns_android_kotlin_digest_for_language_request() -> None:
    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="auto",
        max_tokens=1200,
    )

    assert result["status"] == "success"
    assert result["delivery"]["effective_mode"] == "digest"
    assert result["delivery"]["total_estimated_tokens"] <= 1200
    assert result["skills"][0]["id"] == "android-kotlin"
    assert result["skills"][0]["version"] == "0.0.1"
    assert result["skills"][0]["status"] == "audited"
    assert result["skills"][0]["delivery"] == "digest"
    assert "<local_skill_digest id=\"android-kotlin\"" in result["skills"][0]["content"]
    assert "## Must Follow" in result["skills"][0]["content"]


def test_get_skills_auto_returns_hash_only_for_active_digest() -> None:
    first = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="digest",
    )
    active_hash = first["skills"][0]["hash"]

    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="auto",
        active_hashes=[active_hash],
    )

    assert result["status"] == "success"
    assert result["delivery"]["effective_mode"] == "hash_only"
    assert result["skills"][0]["delivery"] == "hash_only"
    assert result["skills"][0]["content"] == ""
    assert "Reuse the active local skill digest" in result["skills"][0]["instruction"]


def test_get_skills_reports_unmatched_terms_without_dynamic_fetch() -> None:
    result = get_skill_bundle(
        requested_skills=["ios"],
        languages=["swift"],
        mode="auto",
    )

    assert result["status"] == "no_match"
    assert result["skills"] == []
    assert result["unmatched_terms"] == ["ios", "swift"]
    assert "No dynamic network skill lookup was attempted." in result["guidance"]


def test_get_skills_rejects_invalid_delivery_mode() -> None:
    result = get_skill_bundle(
        requested_skills=["android"],
        languages=["kotlin"],
        mode="remote",
    )

    assert result["status"] == "error"
    assert "Invalid mode" in result["message"]


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

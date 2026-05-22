"""Tests for public skill source ingestion."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
import yaml

from scripts.build_skill_store import build_skill_store
from scripts.scan_skill_sources import (
    CandidateSkip,
    assess_risk,
    classify_license,
    normalize_candidate_id,
    parse_skill_markdown,
    scan_local_source,
)
from src.engine.skill_store import SQLiteSkillStore
from src.engine.skills import get_skill_bundle


def _write_skill(
    root: Path,
    relpath: str,
    *,
    name: str = "TDD",
    body: str = "Use tests.",
) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nname: {name}\ndescription: Test workflow.\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return path


def test_parse_skill_markdown_requires_name_description_and_body() -> None:
    parsed = parse_skill_markdown(
        Path("skills/tdd/SKILL.md"),
        "---\nname: TDD\ndescription: Test first.\n---\n\nWrite failing tests first.\n",
    )

    assert parsed["name"] == "TDD"
    assert parsed["description"] == "Test first."
    assert "Write failing tests" in parsed["body"]

    with pytest.raises(CandidateSkip):
        parse_skill_markdown(Path("SKILL.md"), "---\nname: Missing\n---\n\nBody")


def test_normalize_candidate_id_uses_source_and_parent_path() -> None:
    assert (
        normalize_candidate_id(
            "openai-skills",
            Path("skills/.curated/playwright/SKILL.md"),
        )
        == "openai-skills__playwright"
    )
    assert (
        normalize_candidate_id(
            "mattpocock-skills",
            Path("skills/engineering/tdd/SKILL.md"),
        )
        == "mattpocock-skills__engineering-tdd"
    )


def test_license_and_risk_classification(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path, "skills/tdd/SKILL.md", body="Never run rm -rf.")
    (tmp_path / "LICENSE").write_text("MIT License\n", encoding="utf-8")

    license_info = classify_license(tmp_path, skill, {"default_license_policy": "repo"})
    risk = assess_risk(tmp_path, skill, skill.read_text(encoding="utf-8"))

    assert license_info["status"] == "accepted"
    assert license_info["kind"] == "MIT"
    assert risk["level"] == "high"
    assert "mentions_destructive_command" in risk["flags"]


def test_scan_local_source_writes_candidate_manifest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_skill(repo, "skills/engineering/tdd/SKILL.md")
    (repo / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    output_dir = tmp_path / "candidates"
    source = {
        "id": "mattpocock-skills",
        "repo": "mattpocock/skills",
        "url": "https://github.com/mattpocock/skills.git",
        "ref": "main",
        "source_tier": "community",
        "allowed_paths": ["skills/engineering"],
        "skipped_paths": [],
        "default_license_policy": "repo",
        "import_policy": "candidate",
        "max_skill_chars": 60000,
    }

    result = scan_local_source(repo, source, output_dir, commit="abc123")

    assert result["written"] == 1
    manifest_path = (
        output_dir / "mattpocock-skills" / "mattpocock-skills__engineering-tdd.yaml"
    )
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "candidate"
    assert manifest["source"]["commit"] == "abc123"
    assert manifest["license"]["status"] == "accepted"


def test_build_store_loads_candidates_but_get_skills_returns_audited_only(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "skill_registry"
    registry_dir.mkdir()
    (registry_dir / "registry.yaml").write_text(
        "schema_version: local-skill-registry/v0.0.1\nskills: []\n",
        encoding="utf-8",
    )
    candidate_dir = registry_dir / "candidates" / "openai-skills"
    candidate_dir.mkdir(parents=True)
    candidate_dir.joinpath("openai-skills__playwright.yaml").write_text(
        """
schema_version: local-skill-candidate/v0.0.1
id: openai-skills__playwright
name: playwright
description: Browser tests.
status: candidate
source_tier: official
source:
  source_id: openai-skills
  repo: openai/skills
  url: https://github.com/openai/skills.git
  ref: main
  commit: abc123
  path: skills/.curated/playwright/SKILL.md
license:
  status: accepted
  kind: Apache-2.0
  file: LICENSE.txt
risk:
  level: low
  flags: []
facets: [testing, playwright]
languages: []
platforms: []
aliases: [playwright]
content:
  kind: skill_markdown
  sha256: abc
  char_count: 18
  text: Browser testing.
""".strip(),
        encoding="utf-8",
    )
    db_path = tmp_path / "skill_store.sqlite"

    build_skill_store(registry_dir, db_path)

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("select status from skills").fetchone()[0] == "candidate"
    assert SQLiteSkillStore(db_path).search("playwright")[0]["id"] == (
        "openai-skills__playwright"
    )
    result = get_skill_bundle(
        requested_skills=["playwright"],
        mode="auto",
        registry_dir=registry_dir,
        skill_store_path=db_path,
    )
    assert result["status"] == "no_match"
    assert result["skills"] == []

# Skill Source Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an offline pipeline that scans configured public skill repositories, writes reviewable candidate manifests, and loads candidates into the generated SQLite skill store without making them trusted `get_skills` policy.

**Architecture:** Add `skill_registry/sources.yaml` for repository policy, `scripts/scan_skill_sources.py` for offline scanning/parsing/filtering, and candidate support in `scripts/build_skill_store.py`. Keep `get_skills` audited-only by filtering SQLite registry reads, while `SQLiteSkillStore.search()` can find candidate rows for local inspection.

**Tech Stack:** Python 3.10+, standard library `git` subprocess, `tempfile`, `pathlib`, `hashlib`, `re`, `json`; existing `PyYAML==6.0.3`, SQLite FTS5, pytest.

---

## File Structure

- Modify `.gitignore`
  - Ignore generated SQLite artifacts with `*.sqlite`.

- Create `skill_registry/sources.yaml`
  - Static configuration for the five public repositories and phase-one import policies.

- Create `scripts/scan_skill_sources.py`
  - Offline scanner that supports both real GitHub clones and local fake repositories for tests.
  - Writes candidate manifests to `skill_registry/candidates/<source-id>/*.yaml`.

- Modify `scripts/build_skill_store.py`
  - Load candidate manifests in addition to audited registry entries.
  - Reject duplicate IDs.
  - Store candidates/review rows in SQLite.

- Modify `src/engine/skill_store.py`
  - Keep `load_registry()` audited-only.
  - Leave `search()` inclusive so candidates can be inspected locally.

- Create `tests/test_skill_source_ingestion.py`
  - Test parser, path filters, license/risk classification, candidate manifest writing, builder candidate loading, and `get_skills` audited-only behavior.

- Modify `tests/test_skill_store.py`
  - Assert generated stores can contain candidate rows without changing `get_skills`.

## Task 1: Make SQLite Store Generated

**Files:**
- Modify: `.gitignore`
- Remove from Git tracking: `skill_registry/index/skill_store.sqlite`

- [x] **Step 1: Ignore SQLite artifacts**

Add this line after `*.db` in `.gitignore`:

```gitignore
*.sqlite
```

- [x] **Step 2: Stop tracking generated DB**

Run:

```bash
git rm --cached skill_registry/index/skill_store.sqlite
```

Expected: file remains locally but is removed from Git index.

## Task 2: Add Source Configuration

**Files:**
- Create: `skill_registry/sources.yaml`

- [x] **Step 1: Create source policy config**

Create `skill_registry/sources.yaml`:

```yaml
schema_version: local-skill-sources/v0.0.1
sources:
  - id: agentskills
    repo: agentskills/agentskills
    url: https://github.com/agentskills/agentskills.git
    ref: main
    source_tier: standard
    allowed_paths:
      - skills
    skipped_paths: []
    default_license_policy: repo
    import_policy: skip
    max_skill_chars: 60000

  - id: openai-skills
    repo: openai/skills
    url: https://github.com/openai/skills.git
    ref: main
    source_tier: official
    allowed_paths:
      - skills/.curated
    skipped_paths:
      - skills/.system
    default_license_policy: per_skill
    import_policy: candidate
    max_skill_chars: 60000

  - id: anthropic-skills
    repo: anthropics/skills
    url: https://github.com/anthropics/skills.git
    ref: main
    source_tier: official
    allowed_paths:
      - skills
    skipped_paths:
      - template
    default_license_policy: per_skill
    import_policy: candidate
    max_skill_chars: 60000

  - id: awesome-copilot
    repo: github/awesome-copilot
    url: https://github.com/github/awesome-copilot.git
    ref: main
    source_tier: community
    allowed_paths:
      - skills
    skipped_paths:
      - plugins
    default_license_policy: repo
    import_policy: candidate
    max_skill_chars: 60000

  - id: mattpocock-skills
    repo: mattpocock/skills
    url: https://github.com/mattpocock/skills.git
    ref: main
    source_tier: community
    allowed_paths:
      - skills/engineering
    skipped_paths:
      - skills/personal
      - skills/deprecated
      - skills/in-progress
    default_license_policy: repo
    import_policy: candidate
    max_skill_chars: 60000
```

## Task 3: Add Scanner Tests First

**Files:**
- Create: `tests/test_skill_source_ingestion.py`

- [x] **Step 1: Write failing tests**

Create tests for:

```python
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


def _write_skill(root: Path, relpath: str, *, name: str = "TDD", body: str = "Use tests.") -> Path:
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
        normalize_candidate_id("openai-skills", Path("skills/.curated/playwright/SKILL.md"))
        == "openai-skills__playwright"
    )
    assert (
        normalize_candidate_id("mattpocock-skills", Path("skills/engineering/tdd/SKILL.md"))
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
    manifest_path = output_dir / "mattpocock-skills" / "mattpocock-skills__engineering-tdd.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "candidate"
    assert manifest["source"]["commit"] == "abc123"
    assert manifest["license"]["status"] == "accepted"


def test_build_store_loads_candidates_but_get_skills_returns_audited_only(tmp_path: Path) -> None:
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
    assert SQLiteSkillStore(db_path).search("playwright")[0]["id"] == "openai-skills__playwright"
    result = get_skill_bundle(
        requested_skills=["playwright"],
        mode="auto",
        registry_dir=registry_dir,
        skill_store_path=db_path,
    )
    assert result["status"] == "no_match"
    assert result["skills"] == []
```

- [x] **Step 2: Run tests to verify failure**

Run:

```bash
.venv/bin/pytest tests/test_skill_source_ingestion.py -q
```

Expected: import failure because `scripts.scan_skill_sources` does not exist.

## Task 4: Implement Scanner

**Files:**
- Create: `scripts/scan_skill_sources.py`

- [x] **Step 1: Implement scanner functions and CLI**

Implement:

- `CandidateSkip`
- `parse_skill_markdown`
- `normalize_candidate_id`
- `classify_license`
- `assess_risk`
- `scan_local_source`
- `load_sources`
- `scan_sources`
- `main`

Use local temp clones for real repositories and atomic YAML writes for candidates.

- [x] **Step 2: Run scanner tests**

Run:

```bash
.venv/bin/pytest tests/test_skill_source_ingestion.py -q
```

Expected: scanner tests still fail only where builder does not yet load candidates.

## Task 5: Extend Builder And Store For Candidates

**Files:**
- Modify: `scripts/build_skill_store.py`
- Modify: `src/engine/skill_store.py`

- [x] **Step 1: Make SQLite registry reads audited-only**

Change `SQLiteSkillStore.load_registry()` query to:

```sql
from skills where status = 'audited' order by id
```

- [x] **Step 2: Load candidate manifests in builder**

Add candidate loading from `registry_dir / "candidates"`:

- validate `schema_version: local-skill-candidate/v0.0.1`
- reject duplicate IDs
- insert `status` as `candidate` or `review`
- insert candidate `content.text` into `rendered_digest`, `full_content`, and FTS body

- [x] **Step 3: Run skill ingestion tests**

Run:

```bash
.venv/bin/pytest tests/test_skill_source_ingestion.py tests/test_skill_store.py tests/test_skills.py -q
```

Expected: all pass.

## Task 6: Scan Real Sources And Build Store Locally

**Files:**
- Output: `skill_registry/candidates/**/*.yaml`
- Local generated: `skill_registry/index/skill_store.sqlite`

- [x] **Step 1: Run scanner**

Run:

```bash
.venv/bin/python scripts/scan_skill_sources.py --sources skill_registry/sources.yaml
```

Expected: candidate manifests are written and cloned repos are cleaned up.

- [x] **Step 2: Rebuild local store**

Run:

```bash
.venv/bin/python scripts/build_skill_store.py
```

Expected: SQLite store contains audited and candidate/review rows.

- [x] **Step 3: Verify runtime trust boundary**

Run:

```bash
.venv/bin/pytest tests/test_skill_source_ingestion.py tests/test_skill_store.py tests/test_skills.py tests/test_skills_tool.py -q
```

Expected: all pass and `get_skills` remains audited-only.

## Task 7: Final Verification And Amend

**Files:**
- Amend existing branch commit with relevant files only.

- [x] **Step 1: Run full tests**

Run:

```bash
.venv/bin/pytest -q
```

Expected: all tests pass.

- [x] **Step 2: Audit generated files**

Run:

```bash
git status --short
find skill_registry/candidates -type f | wc -l
git ls-files skill_registry/index/skill_store.sqlite
```

Expected:

- candidate manifests are visible in Git status
- `skill_registry/index/skill_store.sqlite` is not tracked

- [x] **Step 3: Amend one branch commit**

Stage only ingestion/local-skill files and run:

```bash
git commit --amend --no-edit
```

Expected: branch still has one commit over `origin/main`.

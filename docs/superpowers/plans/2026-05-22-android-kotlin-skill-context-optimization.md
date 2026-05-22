# Android Kotlin Skill Context Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and audit a PyYAML-backed Android Kotlin skill digest benchmark that compares full markdown context against digest and delta payloads.

**Architecture:** Add a standalone experiment under `experiments/skill_context_optimization/` and a focused test module under `tests/`. The benchmark reads repository Android/Kotlin markdown plus the mobile skill pack zip, renders deterministic digest text from YAML, computes context metrics, and writes JSON/Markdown audit reports without requiring ChromaDB or the MCP server.

**Tech Stack:** Python 3.10+, PyYAML 6.0.3, pytest, standard library `zipfile`, `json`, `time`, and `hashlib`.

---

### Task 1: Add Digest Fixture And Pin PyYAML

**Files:**
- Modify: `pyproject.toml`
- Modify: `docs/superpowers/specs/2026-05-22-android-kotlin-skill-context-optimization-design.md`
- Create: `experiments/skill_context_optimization/android_kotlin_digest.yaml`

- [ ] **Step 1: Pin PyYAML**

Change `pyproject.toml` dependency from:

```toml
"pyyaml>=6.0,<7.0",
```

to:

```toml
"pyyaml==6.0.3",
```

- [ ] **Step 2: Set experiment digest version to 0.0.1**

In the design spec YAML example and actual digest fixture, use:

```yaml
version: 0.0.1
```

- [ ] **Step 3: Create the digest fixture**

Create `experiments/skill_context_optimization/android_kotlin_digest.yaml` with the schema approved in the design spec, scoped to Android Kotlin.

- [ ] **Step 4: Verify YAML parses**

Run:

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
import yaml
path = Path("experiments/skill_context_optimization/android_kotlin_digest.yaml")
data = yaml.safe_load(path.read_text(encoding="utf-8"))
assert data["id"] == "android-kotlin"
assert data["version"] == "0.0.1"
print("ok")
PY
```

Expected: `ok`

### Task 2: Add Benchmark Script

**Files:**
- Create: `experiments/skill_context_optimization/benchmark_android_kotlin_context.py`
- Output: `experiments/skill_context_optimization/android_kotlin_context_audit.json`
- Output: `experiments/skill_context_optimization/android_kotlin_context_audit.md`

- [ ] **Step 1: Write failing tests first**

Tests in Task 3 should initially fail because the benchmark module does not exist.

- [ ] **Step 2: Implement benchmark module**

The module must expose:

```python
estimate_tokens(text: str) -> int
render_digest(data: dict) -> str
load_corpus(project_root: Path, zip_path: Path) -> dict[str, str]
build_audit(project_root: Path, zip_path: Path, digest_path: Path) -> dict
write_reports(audit: dict, output_dir: Path) -> None
main() -> int
```

Use `ceil(len(text) / 4)` for token estimation. Use deterministic string rendering for the digest. Use `zipfile.ZipFile` to read the mobile skill pack without extracting it into the repo.

- [ ] **Step 3: Implement variants**

The audit must include these variants:

```text
full_markdown
current_refinery_summary
yaml_digest
yaml_digest_delta
```

- [ ] **Step 4: Implement pass criteria**

The audit status is `pass` only if:

```text
yaml_digest.reduction_vs_full_percent >= 50
yaml_digest_delta.reduction_vs_full_percent >= 85
hard_rule_retention_percent == 100
noise_ratio <= 25
render_latency_ms < 100
```

### Task 3: Add Tests

**Files:**
- Create: `tests/test_android_kotlin_skill_context_benchmark.py`

- [ ] **Step 1: Test token estimation**

Test:

```python
assert estimate_tokens("") == 0
assert estimate_tokens("abcd") == 1
assert estimate_tokens("abcde") == 2
```

- [ ] **Step 2: Test digest rendering includes required sections**

Load `android_kotlin_digest.yaml`, render it, and assert the output contains `Agent Contract`, `Must Follow`, `Workflow`, `Review Checks`, and `Anti-patterns`.

- [ ] **Step 3: Test hard rule retention**

Build an audit and assert `hard_rule_retention_percent == 100.0`.

- [ ] **Step 4: Test threshold status**

Build an audit and assert `status == "pass"` for the current digest.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
.venv/bin/pytest tests/test_android_kotlin_skill_context_benchmark.py -q
```

Expected: all tests pass.

### Task 4: Run Benchmark And Four Council Rounds

**Files:**
- Output: `experiments/skill_context_optimization/android_kotlin_context_audit.json`
- Output: `experiments/skill_context_optimization/android_kotlin_context_audit.md`

- [ ] **Step 1: Run benchmark**

Run:

```bash
.venv/bin/python experiments/skill_context_optimization/benchmark_android_kotlin_context.py
```

Expected: writes JSON and Markdown audit reports.

- [ ] **Step 2: Council round 1 - tests**

Run:

```bash
.venv/bin/pytest tests/test_android_kotlin_skill_context_benchmark.py -q
```

Expected: pass.

- [ ] **Step 3: Council round 2 - metrics**

Inspect `android_kotlin_context_audit.json` and confirm the pass criteria are met.

- [ ] **Step 4: Council round 3 - content retention**

Inspect the audit hard rule section and confirm every required Kotlin Android hard rule is retained.

- [ ] **Step 5: Council round 4 - integration risk**

Run:

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; only intended feature files changed by this task.

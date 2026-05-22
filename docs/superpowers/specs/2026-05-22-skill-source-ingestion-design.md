# Skill Source Ingestion Pipeline Design

Status: approved for specification review
Date: 2026-05-22
Scope: curated candidate ingestion from public skill repositories into the local skill store pipeline

## Purpose

This design adds an offline pipeline for scanning public skill repositories and
importing filtered skill candidates into the local skill system.

The selected phase-one behavior is:

- Scan configured public repositories.
- Parse and filter `SKILL.md` files.
- Write candidate manifests to `skill_registry/candidates/**`.
- Commit candidate manifests for Git review and audit.
- Keep the SQLite DB as a generated artifact.
- Store candidates in SQLite when the store is rebuilt.
- Keep `get_skills` restricted to `audited` skills only.

This lets the project collect useful skill data without treating unreviewed external
content as trusted runtime policy.

## Current Context

The current local skill path has:

- `skill_registry/registry.yaml` for audited local skills.
- `skill_registry/digests/*.yaml` for curated digest payloads.
- `scripts/build_skill_store.py` for generating `skill_registry/index/skill_store.sqlite`.
- `src/engine/skill_store.py` for SQLite store reads.
- `get_skills` using SQLite first, with YAML fallback, while returning trusted local
  skill payloads to the agent.

The existing SQLite store is static and local, but it only receives audited registry
entries. The next step is to add candidate ingestion while preserving the audited
boundary.

## Source Repositories

Phase one supports these sources:

1. `agentskills/agentskills`
2. `github/awesome-copilot`
3. `anthropics/skills`
4. `openai/skills`
5. `mattpocock/skills`

Repository policy:

- `agentskills/agentskills`
  - Treat as a standard/spec source.
  - Do not import candidates by default because it does not primarily provide
    `SKILL.md` content.
- `openai/skills`
  - Import `skills/.curated/**/SKILL.md`.
  - Skip `skills/.system/**` unless an explicit allowlist is added in a later phase.
- `anthropics/skills`
  - Import skills only when per-skill license status is accepted.
  - Mark source-available or unclear license skills as `review`.
- `github/awesome-copilot`
  - Import direct `skills/**/SKILL.md` first.
  - Skip `plugins/**/skills/**` in phase one to reduce volume and review noise.
- `mattpocock/skills`
  - Import `skills/engineering/**/SKILL.md`.
  - Skip `skills/personal/**`, `skills/deprecated/**`, and `skills/in-progress/**`.

## Non-Goals

This phase does not:

- Promote external skills to `audited`.
- Allow `get_skills` to return `candidate` content.
- Fetch repositories during MCP runtime.
- Execute scripts from imported skills.
- Import plugin skills from `awesome-copilot`.
- Add embeddings or mandatory vector search.
- Build a UI or marketplace.
- Automatically update the committed candidate set on a schedule.

## Recommended Approach

Use a manifest-first ingestion pipeline.

Add a source configuration file:

```text
skill_registry/sources.yaml
```

Add an offline scanner:

```text
scripts/scan_skill_sources.py
```

The scanner reads configured sources, clones or fetches them into a temporary work
area, discovers allowed `SKILL.md` files, parses and filters them, and writes candidate
manifests:

```text
skill_registry/candidates/<source-id>/<candidate-id>.yaml
```

The SQLite builder then loads both:

- audited entries from `skill_registry/registry.yaml`
- candidate entries from `skill_registry/candidates/**/*.yaml`

Runtime `get_skills` remains audited-only.

## Alternatives Considered

### Option A: Candidate Manifests Plus Generated SQLite

This is the selected approach.

Pros:

- Candidate data is reviewable in Git.
- SQLite remains rebuildable and generated.
- Audited and candidate states stay separate.
- Candidate filters can evolve without changing runtime trust rules.

Cons:

- Adds a manifest schema and scanner.
- Large candidate sets may still create noisy diffs if filters are too broad.

### Option B: Direct SQLite Import

Pros:

- Smaller Git diffs.
- Faster initial import.

Cons:

- Candidates are harder to review.
- The DB becomes the only place to inspect imported data.
- Promotion decisions lose clear file-level provenance.

### Option C: Append Candidates To `registry.yaml`

Pros:

- Simpler builder changes.
- All skills live in one registry file.

Cons:

- Mixes audited and untrusted content too early.
- Makes registry review noisy.
- Increases risk that `candidate` entries accidentally become trusted policy.

## Architecture

Add four units:

1. `skill_registry/sources.yaml`
   - Static source policy.
   - Defines repositories, refs, allowed paths, skipped paths, source tier, and license
     policy.

2. `scripts/scan_skill_sources.py`
   - Offline ingestion scanner.
   - Uses `git clone --depth 1 --filter=blob:none` where practical.
   - Performs sparse checkout for configured paths when possible.
   - Parses `SKILL.md` frontmatter and body.
   - Applies schema, license, and risk filters.
   - Writes candidate YAML manifests.

3. `skill_registry/candidates/**/*.yaml`
   - Generated-but-committed candidate manifests.
   - Human-reviewable promotion source.
   - Not trusted by `get_skills`.

4. `scripts/build_skill_store.py`
   - Extends existing builder.
   - Loads candidate manifests after audited registry entries.
   - Stores `candidate` and `review` rows in SQLite.
   - Keeps `audited` matching behavior unchanged for `get_skills`.

## Source Configuration Schema

Initial `skill_registry/sources.yaml` schema:

```yaml
schema_version: local-skill-sources/v0.0.1
sources:
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
```

Required fields:

- `id`
- `repo`
- `url`
- `ref`
- `source_tier`
- `allowed_paths`
- `import_policy`

Optional fields:

- `skipped_paths`
- `default_license_policy`
- `max_skill_chars`
- `include_patterns`
- `exclude_patterns`

## Candidate Manifest Schema

Candidate manifests use:

```yaml
schema_version: local-skill-candidate/v0.0.1
id: openai-skills__playwright
name: playwright
description: Browser automation and test workflow support.
status: candidate
source:
  source_id: openai-skills
  repo: openai/skills
  url: https://github.com/openai/skills.git
  ref: main
  commit: <resolved_commit_sha>
  path: skills/.curated/playwright/SKILL.md
source_tier: official
license:
  status: accepted
  kind: Apache-2.0
  file: skills/.curated/playwright/LICENSE.txt
risk:
  level: low
  flags: []
facets:
  - testing
languages: []
platforms: []
aliases:
  - playwright
content:
  kind: skill_markdown
  sha256: <sha256_of_full_skill_md>
  char_count: 1234
  text: |
    # Body without YAML frontmatter
```

The manifest stores body text so SQLite can be rebuilt without recloning the source
repository. Later promotion work can transform candidate manifests into curated digest
YAML.

## Filtering Rules

Schema gates:

- Accept only files named `SKILL.md`.
- Require YAML frontmatter.
- Require `name` and `description`.
- Require body content after frontmatter.
- Reject files above `max_skill_chars`, unless the source config explicitly raises the
  limit.

Path gates:

- File path must be under one configured `allowed_paths`.
- File path must not be under `skipped_paths`.

License gates:

- `accepted`: MIT, Apache-2.0, or source policy that explicitly accepts the repo license.
- `review`: missing license, source-available license, custom license, or unclear
  per-skill license.
- `rejected`: explicit incompatible license.

Risk gates:

- Candidate remains importable when risk is `low` or `medium`.
- Candidate is skipped when risk is `high`.
- Scanner records flags instead of executing or interpreting scripts.

Initial risk flags:

- `has_scripts_directory`
- `has_references_directory`
- `has_assets_directory`
- `mentions_network_install`
- `mentions_destructive_command`
- `mentions_secret_or_token`
- `mentions_external_api`
- `personal_workflow`

Status mapping:

- accepted license + low/medium risk -> `candidate`
- review license + low/medium risk -> `review`
- rejected license or high risk -> skipped with report entry

## Normalization Rules

Candidate IDs must be deterministic:

```text
<source-id>__<normalized-skill-path-parent>
```

Examples:

- `openai-skills__playwright`
- `mattpocock-skills__engineering-tdd`
- `awesome-copilot__python-pypi-package-builder`

Normalization:

- lowercase
- replace path separators and whitespace with `-`
- preserve alphanumeric text
- collapse repeated separators

Facet inference is deliberately conservative:

- Path segments become low-confidence facets.
- Known keywords map to facets such as `testing`, `security`, `frontend`, `mcp`,
  `python`, `typescript`, `documentation`.
- The scanner does not invent audited policy facets.

## SQLite Store Behavior

Extend the store schema or rows to represent candidates:

- `status` can be `audited`, `candidate`, or `review`.
- `source_json` includes full candidate provenance.
- Candidate rows are inserted into `skills` and `skill_fts`.
- Candidate body text is indexed for FTS search.

`get_skills` behavior:

- `get_skills` must only match rows with `status="audited"`.
- Existing YAML fallback remains audited-only.
- Candidate entries cannot be returned as `<local_skill_digest>`.

Search behavior:

- Existing `SQLiteSkillStore.search()` may include candidates by default for local
  inspection.
- A future `search_skills` MCP tool can expose candidates with clear status labels.

## Error Handling

Scanner errors:

- Invalid `sources.yaml` fails the scan before network work.
- Clone/fetch failure records the failed source and exits non-zero unless
  `--continue-on-error` is provided.
- Invalid `SKILL.md` frontmatter records a skipped candidate.
- License/risk rejection records a skipped candidate.
- Candidate output writes atomically per file.

Builder errors:

- Malformed candidate YAML fails the build.
- Duplicate skill IDs fail the build.
- Candidate schema mismatch fails the build.
- SQLite FTS5 absence still fails the build.

Runtime errors:

- Runtime does not clone, scan, or fetch.
- Runtime ignores candidate rows for `get_skills`.
- Runtime fallback behavior stays unchanged when SQLite is missing or invalid.

## Testing Strategy

Use fake local repositories in temporary directories. Tests must not require network.

Add tests for:

- `sources.yaml` parsing and validation.
- `SKILL.md` frontmatter parsing.
- Allowed path and skipped path behavior.
- License classification.
- Risk flag classification.
- Candidate manifest writing.
- Builder loading candidate manifests into SQLite.
- `SQLiteSkillStore.search()` finding a candidate row.
- `get_skill_bundle()` not returning candidate-only matches.
- Duplicate candidate IDs failing the build.

## Operational Workflow

Manual update flow:

```bash
python3 scripts/scan_skill_sources.py --sources skill_registry/sources.yaml
python3 scripts/build_skill_store.py
pytest tests/test_skill_source_ingestion.py tests/test_skill_store.py tests/test_skills.py -q
```

Review flow:

1. Review generated `skill_registry/candidates/**/*.yaml`.
2. Promote selected candidates manually in a later phase by writing curated digest YAML
   and audited registry entries.
3. Rebuild SQLite store.

## Audit Criteria

Implementation is acceptable when:

- Scanner commits no cloned repository content.
- Candidate manifests are deterministic and reviewable.
- SQLite DB remains generated.
- `get_skills` still returns only audited entries.
- Candidate search is possible through the local store adapter.
- Tests run without network.
- No code path executes imported skill scripts.
- All existing skill-store tests continue to pass.

## Future Work

Later phases can add:

- Promotion command from candidate manifest to audited digest draft.
- Optional `search_skills` MCP tool.
- Optional sqlite-vec embeddings for candidates.
- Scheduled refresh automation.
- Plugin skill ingestion from `awesome-copilot`.
- Richer license policy files.

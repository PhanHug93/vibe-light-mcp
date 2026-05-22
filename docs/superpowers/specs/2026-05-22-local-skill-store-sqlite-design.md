# Local Skill Store SQLite Design

Status: approved for specification review
Date: 2026-05-22
Scope: SQLite-first local skill store for audited MCP skill delivery

## Purpose

This design moves local skill lookup toward a durable, static, local store that is
independent of the current ChromaDB vector database used for L1/L2 memory.

The immediate goal is a runtime-safe transition:

- Build a SQLite skill store from the existing audited `skill_registry` YAML files.
- Make `get_skills` read from SQLite first.
- Fall back to the current YAML registry when the SQLite store is missing or invalid.
- Require SQLite FTS5 for keyword search.
- Treat `sqlite-vec` as optional, not required for the first implementation.

This keeps existing `get_skills` behavior stable while creating a long-term storage
boundary for local skills.

## Current Context

The repository already has two skill paths:

- `skill_registry/registry.yaml` and `skill_registry/digests/*.yaml` define audited
  local skill digests for `get_skills`.
- `scripts/import_skills.sh` and `scripts/seed_skills.py` import external `SKILL.md`
  content into ChromaDB L2 memory.

The second path is useful for broad knowledge import, but it is not the right durable
source of truth for local skills. Skills are curated executable policy artifacts, not
ordinary memory chunks. They need source provenance, audit status, license state,
stable hashes, deterministic rebuilds, and fallback behavior.

## Non-Goals

This phase does not:

- Replace ChromaDB for memory.
- Remove the existing YAML registry.
- Fetch GitHub repositories dynamically during MCP runtime.
- Require `sqlite-vec` or any native vector extension.
- Import the public skill repositories directly.
- Add a full marketplace or remote sync system.

## Recommended Approach

Use SQLite as the local skill store, with FTS5 required and vector support optional.

The implementation should add a build-time artifact:

```text
skill_registry/index/skill_store.sqlite
```

The artifact is generated from checked-in registry and digest files. MCP runtime reads
it locally. If it is absent, unreadable, or has an unsupported schema version, runtime
falls back to the existing YAML path.

## Alternatives Considered

### Option A: SQLite First, FTS5 Required, sqlite-vec Optional

This is the selected approach.

Pros:

- Single local file, easy to backup and rebuild.
- No dependency on the ChromaDB service.
- FTS5 supports exact keyword and alias search, which is critical for skills.
- Optional vector search can be added without making runtime fragile.
- Existing YAML behavior can remain as fallback.

Cons:

- First version has no mandatory vector ranking.
- Requires a small internal storage adapter.

### Option B: SQLite Plus Mandatory sqlite-vec

Pros:

- Enables hybrid keyword and vector retrieval immediately.
- Aligns directly with the long-term vector-search goal.

Cons:

- Adds native extension installation risk.
- Increases CI and packaging complexity.
- Not necessary for the current `get_skills` exact/facet lookup use case.

### Option C: SQLite Manifest Only

Pros:

- Lowest implementation risk.
- Simple replacement for YAML loading.

Cons:

- Does not improve search and filtering enough.
- Defers too much of the core value.

## Architecture

Add three isolated units:

1. `scripts/build_skill_store.py`
   - Offline builder.
   - Reads `skill_registry/registry.yaml`.
   - Reads each referenced digest.
   - Validates schema and FTS5 availability.
   - Writes `skill_registry/index/skill_store.sqlite`.

2. `src/engine/skill_store.py`
   - SQLite read adapter.
   - Opens the store read-only when possible.
   - Checks schema version.
   - Provides skill lookup and FTS search helpers.
   - Has no ChromaDB dependency.

3. `src/engine/skills.py`
   - Keeps the public `get_skill_bundle` API.
   - Attempts SQLite-first lookup.
   - Falls back to existing YAML registry lookup.
   - Preserves response schema and delivery modes.

This keeps build, storage, and payload rendering separate.

## Data Model

Initial SQLite schema:

```sql
metadata(
  key text primary key,
  value text not null
);

skills(
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

skill_fts using fts5(
  skill_id unindexed,
  name,
  description,
  aliases,
  facets,
  body
);
```

Required metadata:

```text
schema_version=local-skill-store/v0.0.1
builder_version=0.0.1
created_at=<UTC ISO timestamp>
source_registry=<absolute registry.yaml path>
vector_enabled=false
```

The first implementation stores rendered digest text directly in SQLite so runtime
does not need to re-render YAML for the SQLite path. It still stores `digest_path` and
source metadata for provenance and fallback clarity.

## Data Flow

Build flow:

```text
skill_registry/registry.yaml
  -> registry entries
  -> digests/*.yaml
  -> render digest text
  -> hash rendered digest
  -> populate skills + skill_fts
  -> atomic replace skill_store.sqlite
```

Runtime flow:

```text
get_skill_bundle(request)
  -> validate request terms and mode
  -> try SQLite store
       -> match by requested skills/languages against metadata
       -> build payload from rendered digest/full content
  -> on missing or invalid store, use YAML fallback
  -> return existing local-skills-response/v0.0.1 shape
```

Search flow:

```text
search terms
  -> metadata filters first
  -> FTS5 match second
  -> deterministic source/status ordering
```

## Matching Rules

For `get_skills`, SQLite matching must preserve the current YAML semantics:

- Normalize requested skills and languages the same way as the current engine.
- Match requested skills against `id`, `aliases`, `facets`, `platforms`, and
  `languages`.
- Match language constraints against `languages`.
- Require at least one requested skill or language.
- Sort by confidence descending, then skill id.

FTS5 should not change `get_skills` matching in this phase. It is used for search
support and future ranking.

## Delivery Modes

The existing modes remain:

- `auto`
- `digest`
- `hash_only`
- `delta`
- `full`

SQLite-first delivery must preserve current behavior:

- `auto` returns `hash_only` when the active hash matches.
- `delta` returns `hash_only` in this phase.
- `digest` returns the rendered digest wrapper.
- `full` returns rendered digest plus available full source content.
- Token budget failures return the current error shape.

## Error Handling

SQLite path should fall back to YAML when:

- The DB file does not exist.
- SQLite cannot open the DB.
- `metadata.schema_version` is missing or unsupported.
- Required tables are missing.
- Store rows are malformed.

SQLite path should raise a clear build-time error when:

- `skill_registry/registry.yaml` cannot be parsed.
- A referenced digest is missing.
- A digest cannot be rendered.
- FTS5 is unavailable in the Python SQLite build.
- Atomic write or replace fails.

`sqlite-vec` absence is not an error. The builder records `vector_enabled=false`.

## Configuration

Add one path constant:

```python
SKILL_STORE_PATH = SKILL_REGISTRY_DIR / "index" / "skill_store.sqlite"
```

No environment variable is needed in the first phase. A future phase may add
`MCP_SKILL_STORE_PATH` if users need an external store location.

## Testing Strategy

Add focused tests for:

- Builder creates a SQLite DB from the current registry.
- Generated DB includes schema metadata and the Android Kotlin skill.
- FTS5 search can find `android-kotlin` using terms such as `android`, `kotlin`,
  and `lifecycle`.
- `get_skill_bundle` returns the same successful Android Kotlin digest through the
  SQLite-first path.
- Missing DB falls back to YAML and still returns the current successful payload.
- Existing invalid mode and token budget behavior remains unchanged.

The tests should use temporary store paths where practical so they do not depend on a
prebuilt committed SQLite artifact.

## Migration And Compatibility

This is an additive change.

The current YAML registry remains source of truth. The SQLite DB is a generated local
index, not the canonical editable format. If the store is stale or missing, MCP still
serves audited skills from YAML.

The old `scripts/import_skills.sh` and `scripts/seed_skills.py` remain unchanged in
this phase. A later design can deprecate ChromaDB skill import or repoint it at the new
offline scanner.

## Audit Criteria

Implementation is acceptable when:

- ChromaDB is not imported or contacted by the new skill store code path.
- `get_skills` works with a valid SQLite store.
- `get_skills` works without a SQLite store through YAML fallback.
- FTS5 is verified during store build.
- `sqlite-vec` is optional and absence does not break tests.
- Existing `tests/test_skills.py` and `tests/test_skills_tool.py` pass.
- New tests cover builder, SQLite lookup, FTS search, and fallback.

## Future Work

Later phases can add:

- `skill_sources.yaml` for pinned external repo ingestion.
- License and script risk gates for imported public skills.
- Optional `sqlite-vec` vector tables and offline embeddings.
- A `search_skills` MCP tool.
- Store freshness checks based on registry and digest hashes.
- A cleanup path for the older ChromaDB skill import workflow.

# Android Kotlin Skill Context Optimization Design

Status: approved for planning
Date: 2026-05-22
Scope: Kotlin Android local skill context optimization only

## Purpose

This design defines a controlled experiment for optimizing the skill context that an
AI agent receives when working on Kotlin Android code. The goal is to move from raw
markdown skill delivery toward a deterministic, structured YAML digest that is shorter,
cleaner, auditable, and suitable as the foundation for a future `get_skills` MCP tool.

The experiment must not change runtime MCP behavior yet. It produces standalone audit
artifacts so the optimization can be evaluated before being integrated into the server.

## Current Context

The repository already declares PyYAML in `pyproject.toml` as `pyyaml>=6.0,<7.0`, and
the stack detector already uses YAML for `tech_stacks/registry.yaml`.

The current Android/Kotlin knowledge surface is split across:

- `tech_stacks/android_kotlin/rules.md`, which contains high-value development policy.
- `tech_stacks/android_kotlin/skills.md`, which mostly contains terminal commands.

The user-provided `mobile-local-skills-pack-v1.1.1.zip` adds richer mobile skills that
cover Android Compose, Android XML/View, Android custom View/Canvas, legacy mobile
maintenance, testing, and performance.

## Dependency Decision

Pin PyYAML to a fixed stable version for this experiment:

```toml
pyyaml==6.0.3
```

PyYAML is not used as a context compression algorithm. It is used to load a structured
digest schema. Context savings come from rendering a curated digest instead of sending
raw markdown.

## Corpus

The benchmark corpus combines repository-local Android/Kotlin knowledge with the
Android-related subset of the mobile local skill pack.

Repository baseline sources:

- `tech_stacks/android_kotlin/rules.md`
- `tech_stacks/android_kotlin/skills.md`

Mobile skill pack candidate sources:

- `skills/android-kotlin-compose.md`
- `skills/android-kotlin-xml-views.md`
- `skills/android-custom-view-canvas.md`
- `skills/legacy-mobile-maintenance.md`
- `skills/testing-quality.md`
- `skills/performance-observability.md`

The first experiment excludes iOS, Flutter, KMP, Electron, release, and security unless
they are needed by a later follow-up.

## YAML Digest Schema

The digest file should live at:

```text
experiments/skill_context_optimization/android_kotlin_digest.yaml
```

Initial schema:

```yaml
id: android-kotlin
version: 0.0.1
source_pack:
  name: local-mcp-server/android_kotlin
  pyyaml_version: "6.0.3"

applies_to:
  facets: [android, kotlin]
  project_signals:
    - build.gradle
    - build.gradle.kts
    - .kt
    - Fragment
    - ViewModel
    - StateFlow
    - RecyclerView
    - "@Composable"

agent_contract:
  primary_instruction: "Use this local Kotlin Android skill policy before implementing or reviewing Android code."
  apply_order:
    - android-kotlin-core
    - android-lifecycle-state
    - android-testing-quality
  confidence_floor: 0.75

must_follow:
  - Keep business logic out of Fragment, Activity, Composable, and Adapter.
  - Use ViewModel plus StateFlow for UI state.
  - Collect Flow from Fragment with viewLifecycleOwner and repeatOnLifecycle.
  - Do not use GlobalScope or runBlocking in production code.
  - Do not log Authorization headers, PII, tokens, or raw sensitive JSON.
  - Add regression coverage before changing behavior-critical legacy code.

workflow:
  - Detect UI style: XML/View, Compose, custom View, or mixed legacy.
  - Identify state owner and side effects.
  - Check lifecycle, coroutine, navigation, network, and persistence boundaries.
  - Select the smallest safe implementation path.
  - Run relevant test/build command or provide a concrete verification gap.

review_checks:
  - Fragment binding cleanup
  - lifecycle-aware collection
  - one-shot event handling
  - RecyclerView diffing and stable identity
  - raw exception exposure
  - network token refresh race
  - secret logging
  - main-thread blocking IO

anti_patterns:
  - Direct Retrofit call from ViewModel.
  - Business logic inside Fragment or Adapter.
  - Multiple LiveData flags for loading, data, and error.
  - notifyDataSetChanged for normal list updates.
  - Storing Context in Singleton.
  - Catching Exception and ignoring it.

full_content_sources:
  - tech_stacks/android_kotlin/rules.md
  - tech_stacks/android_kotlin/skills.md
  - mobile-local-skills-pack-v1.1.1/skills/android-kotlin-compose.md
  - mobile-local-skills-pack-v1.1.1/skills/android-kotlin-xml-views.md
  - mobile-local-skills-pack-v1.1.1/skills/android-custom-view-canvas.md
  - mobile-local-skills-pack-v1.1.1/skills/legacy-mobile-maintenance.md
  - mobile-local-skills-pack-v1.1.1/skills/testing-quality.md
  - mobile-local-skills-pack-v1.1.1/skills/performance-observability.md
```

## Benchmark Variants

The standalone benchmark should compare four variants:

1. `full_markdown`: all corpus markdown concatenated.
2. `current_refinery_summary`: heading and bullet summary, approximating current refinery behavior.
3. `yaml_digest`: rendered digest text from the YAML schema.
4. `yaml_digest_delta`: simulated follow-up payload containing only bundle id, hashes, and changed/new digest items.

The token estimator should initially match the repository's current heuristic:

```text
estimated_tokens = ceil(char_count / 4)
```

This avoids tying the benchmark to one model provider's tokenizer.

## Metrics

Each variant should report:

- `char_count`
- `estimated_tokens`
- `reduction_vs_full_percent`
- `hard_rule_retention_percent`
- `noise_ratio`
- `render_latency_ms`
- `source_count`

## Hard Rule Retention

The audit must verify that the digest retains these rules:

- No business logic in Fragment, Activity, Composable, or Adapter.
- Use lifecycle-aware Flow collection.
- No `GlobalScope` or `runBlocking` in production code.
- Do not expose raw exceptions to UI.
- Do not log tokens, PII, Authorization headers, or raw sensitive JSON.
- Add regression coverage before behavior-critical legacy changes.
- Do not rewrite legacy XML/View/custom View without tests and rollback.
- Use RecyclerView diffing or stable identity where appropriate.
- No main-thread blocking IO.

The first implementation may use deterministic keyword checks for this audit. A later
version can add semantic checks if deterministic retention is not enough.

## Pass Criteria

The experiment passes when:

- `yaml_digest.reduction_vs_full_percent >= 50`
- `yaml_digest_delta.reduction_vs_full_percent >= 85`
- `hard_rule_retention_percent == 100`
- `noise_ratio <= 25`
- `render_latency_ms < 100` on the local machine

If a metric fails, the report should mark the experiment as `fail` and list the exact
failed criteria.

## Output Artifacts

The benchmark should write:

```text
experiments/skill_context_optimization/android_kotlin_digest.yaml
experiments/skill_context_optimization/android_kotlin_context_audit.json
experiments/skill_context_optimization/android_kotlin_context_audit.md
```

The JSON report is for machine review and regression tests. The Markdown report is for
human review.

## Error Handling

The benchmark should fail clearly when:

- PyYAML is not importable in the selected Python environment.
- The zip file is missing from `/Users/admin/Downloads/mobile-local-skills-pack-v1.1.1.zip`.
- A required corpus source is missing inside the repository or zip.
- The YAML digest cannot be parsed.
- A hard rule is not retained in the rendered digest.

The script should not require ChromaDB or a running MCP server.

## Testing Strategy

Add focused tests for:

- YAML digest parseability.
- Required schema fields.
- Hard rule retention.
- Benchmark pass/fail threshold logic.
- Rendering stability for agent-ready digest text.

Run the standalone benchmark after implementation and include the produced audit
numbers in the final implementation summary.

## Future Integration

If the experiment passes, the next feature should use the digest as the foundation for
`get_skills` delivery modes:

- `full`
- `digest`
- `hash_only`
- `delta`
- `auto`

This design deliberately stops before adding the MCP tool so the context optimization
can be measured independently.

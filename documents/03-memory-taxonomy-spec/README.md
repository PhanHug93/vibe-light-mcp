# 03. Memory Taxonomy Spec

Status: draft
Owner: architecture
Last updated: 2026-04-08

## Purpose

This folder defines the canonical taxonomy for all memory and runtime artifacts inside
the MCP platform.

The taxonomy exists to solve one core problem:

- the system now has both durable memory and executor-facing runtime state
- if these artifacts are not classified explicitly, retrieval semantics will drift and
  the durable database will get polluted over time

## Design Goal

Use the smallest taxonomy that still gives us:

1. clean retrieval boundaries
2. safe promotion boundaries
3. explicit retention behavior
4. predictable debug visibility

This spec intentionally avoids over-modeling. Too many artifact classes will make the
system harder to reason about and easier to misuse.

## Canonical Artifact Families

The current proposal uses six primary artifact families:

1. `workspace_durable`
2. `global_durable`
3. `session_scratch`
4. `payload_metadata_cache`
5. `source_manifest`
6. `retry_capsule`

In addition, promotion uses a transient governance state:

7. `promotion_candidate`

## Folder Structure

- [01-taxonomy-overview.md](./01-taxonomy-overview.md)
- [02-artifact-families.md](./02-artifact-families.md)
- [03-required-metadata.md](./03-required-metadata.md)
- [04-visibility-retention-and-searchability.md](./04-visibility-retention-and-searchability.md)
- [05-logical-taxonomy-vs-physical-storage-mapping.md](./05-logical-taxonomy-vs-physical-storage-mapping.md)
- [06-design-risks-and-review-points.md](./06-design-risks-and-review-points.md)
- [07-three-core-rules-v1.md](./07-three-core-rules-v1.md)
- [08-validation-gate-v1.md](./08-validation-gate-v1.md)
- [09-durable-artifact-metadata-v1.md](./09-durable-artifact-metadata-v1.md)
- [specializations/README.md](./specializations/README.md)

## Review Goal

This folder should answer:

1. What artifact types exist?
2. What is each type allowed to do?
3. Who can read each type?
4. Which types are searchable?
5. Which types may be promoted?

## Note On Scope

Artifact-type specialization docs under `specializations/` are currently versioned as
`V1`. In this project, `V1` means "temporarily locked for the current design scope",
not "final forever".

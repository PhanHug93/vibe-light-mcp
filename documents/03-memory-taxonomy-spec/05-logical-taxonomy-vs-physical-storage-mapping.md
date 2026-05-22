# Logical Taxonomy Vs Physical Storage Mapping

Status: draft

## Purpose

This document prevents a common architecture mistake:

- treating every logical artifact family as a separate physical storage class too early

The taxonomy in `03` is primarily a policy model. It exists to define:

- retention behavior
- searchability
- visibility
- promotion eligibility
- governance requirements

It does not require a one-to-one storage implementation on day one.

## Principle

Logical taxonomy answers:
- what the artifact is allowed to do

Physical storage mapping answers:
- where the artifact is actually stored and operated

These two layers must be related, but they should not be tightly coupled too early.

## Why A Direct 1:1 Mapping Is Risky

If every artifact family becomes a dedicated storage surface immediately, the system
pays a complexity tax across:

- write amplification
- cleanup complexity
- backup and migration complexity
- observability fragmentation
- mental model overhead for engineers and agents

That design can be correct eventually, but it is usually too expensive for the first
operational versions of a dual-purpose MCP.

## Recommended Layering

### Logical Layer

The logical taxonomy remains explicit:

1. `workspace_durable`
2. `global_durable`
3. `session_scratch`
4. `payload_metadata_cache`
5. `source_manifest`
6. `retry_capsule`
7. `promotion_candidate`

### Physical Layer V1

The first physical implementation should stay intentionally small:

1. `durable_workspace_store`
2. `durable_global_store`
3. `session_runtime_store`
4. `gateway_ops_store`

This gives the system enough separation to stay safe, without turning the MCP into an
over-segmented data platform before the operational model is proven.

## Recommended Mapping

| Logical Artifact Family | Recommended Physical Store V1 | Why |
|---|---|---|
| `workspace_durable` | `durable_workspace_store` | project-specific durable knowledge needs clear retrieval and cleanup boundaries |
| `global_durable` | `durable_global_store` | cross-project durable knowledge needs stricter governance and lower write frequency |
| `session_scratch` | `session_runtime_store` | isolated working context must stay separate from durable retrieval |
| `payload_metadata_cache` | `gateway_ops_store` | operational metadata belongs with retry and observability artifacts |
| `source_manifest` | `gateway_ops_store` | source lineage is operational support data, not retrieval knowledge |
| `retry_capsule` | `gateway_ops_store` | replay support should remain ephemeral and operational |
| `promotion_candidate` | `gateway_ops_store` or governance queue | governance staging should stay outside normal retrieval paths |

## Physical Store Responsibilities

### `durable_workspace_store`

Contains:
- `workspace_durable`

Behavior:
- searchable
- human-readable retrieval source
- medium to long retention
- shared per project

### `durable_global_store`

Contains:
- `global_durable`

Behavior:
- searchable
- human-readable retrieval source
- longest retention
- highest promotion threshold

### `session_runtime_store`

Contains:
- `session_scratch`

Behavior:
- isolated by agent/session policy
- readable by gateway flows
- not part of human recall by default
- short retention

### `gateway_ops_store`

Contains:
- `payload_metadata_cache`
- `source_manifest`
- `retry_capsule`
- `promotion_candidate` or equivalent staging state

Behavior:
- not part of normal human retrieval
- used for retry classification, observability, governance staging, and operational debugging
- short retention by default
- content visibility remains restricted

## Why `gateway_ops_store` Should Exist

This store groups runtime operational artifacts that:

- are not durable knowledge
- should not pollute session scratch
- may need different cleanup and access policy from human memory

Without this store, there is a strong temptation to push retry and diagnostics data into
session memory or durable memory, which is exactly the wrong direction.

## Retrieval Constraint

The physical mapping must not change the retrieval contract:

- human retrieval reads durable stores only
- gateway retrieval reads `session_runtime_store` plus durable stores
- `gateway_ops_store` does not participate in normal retrieval

This is a hard guardrail. If `gateway_ops_store` starts feeding normal retrieval, the
system will begin reusing operational artifacts as if they were knowledge.

## Phase-Based Evolution

### Phase 1

Keep physical stores minimal:

- durable workspace
- durable global
- session runtime
- gateway ops

### Phase 2

Split a physical store only if one of the following becomes true:

- retention policy differs materially
- security policy differs materially
- throughput profile differs materially
- migration and backup policy differ materially
- operational contention becomes visible

### Phase 3

Only then consider specialized physical stores such as:

- dedicated governance queue store
- dedicated replay capsule store
- dedicated observability store

## Anti-Pattern To Avoid

Do not let the team assume:

- "different artifact family" automatically means "different database collection"

That assumption creates unnecessary infrastructure and does not improve policy clarity.

## Design Recommendation

The correct posture for this MCP is:

- logical taxonomy should be rich enough to protect semantics
- physical storage should be conservative enough to keep operations manageable

This is the balance point between architecture integrity and operating simplicity.

# Required Metadata

Status: draft

## Principle

The system must not infer artifact behavior from content shape alone.

Every stored artifact must carry enough metadata to answer:

- what it is
- where it came from
- who may read it
- how long it should live
- whether it may be promoted

## Minimum Required Metadata

Every artifact should carry:

- `artifact_family`
- `artifact_type`
- `workspace_id`
- `origin_plane`
- `created_at`
- `created_by`
- `retention_class`
- `visibility_class`
- `searchable`
- `promotion_state`
- `sanitization_status`

## Scope Metadata

Artifacts that are not global must also carry:

- `memory_scope`
- `agent_id` when session-scoped
- `session_id` when applicable
- `session_namespace` when applicable

## Governance Metadata

Artifacts eligible for promotion or already promoted should additionally carry:

- `verification_tier`
- `score_total`
- `score_breakdown`
- `evidence_refs`
- `origin_refs`
- `last_validated_at`

## Operational Metadata

Gateway-side runtime artifacts may additionally carry:

- `request_id`
- `input_digest`
- `source_tiers_accessed`
- `token_budget_requested`
- `token_budget_used`
- `latency_ms`
- `drop_reasons`

## Hard Rule

No artifact should enter storage without an explicit `artifact_family`.

If this rule is violated, later retrieval and cleanup logic will become implicit and fragile.

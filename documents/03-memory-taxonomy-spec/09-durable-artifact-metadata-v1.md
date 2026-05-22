# Durable Artifact Metadata V1

Status: draft
Scope note: `V1` means temporarily locked for the current design scope.

## Purpose

This document defines the metadata header for artifacts stored in:

- `workspace_durable`
- `global_durable`

This is a durable governance header, not the full artifact content schema.

It exists to support:

- retrieval ranking
- validation and revalidation
- auditability
- confidence decay
- lineage and conflict handling

## Design Constraints

The durable metadata header should be:

- stable
- low-churn
- auditable
- human-governable

It should not absorb hot operational fields that change frequently during retrieval.

## What Belongs In This Header

The header should contain:

1. identity and scope
2. state and visibility
3. validation and confidence
4. freshness and revalidation
5. evidence refs
6. applicability
7. lineage and relationships

## What Does Not Belong In This Header

The following should live in sidecar stores or telemetry layers:

- high-frequency usage counters
- feedback events
- event logs
- retrieval serving weights
- write-on-read state

These are operational concerns, not durable core metadata.

## Recommended Header Shape

```json
{
  "schema_version": "durable-artifact/v1",
  "artifact_id": "art_123",
  "artifact_family": "workspace_durable",
  "artifact_type": "PRINCIPLE",
  "workspace_id": "ws_abc",

  "artifact_state": "ACTIVE",
  "sanitization_status": "SANITIZED",
  "human_readable": true,
  "searchable": true,

  "created_at": "2026-04-08T10:20:00Z",

  "last_validated_at": "2026-04-08T10:32:00Z",
  "validated_by": {
    "actor_type": "SYSTEM",
    "actor_id": "promotion_gate"
  },
  "validation_mode": "AUTO",
  "verification_tier": "EVIDENCE_BACKED",

  "confidence": {
    "score": 0.82,
    "model_version": "v1",
    "reason": {
      "signals": ["REPETITION", "EXECUTION_EVIDENCE"],
      "details": {
        "occurrence_count": 3,
        "evidence_count": 2,
        "cross_session_count": 2
      }
    }
  },

  "freshness": {
    "revalidation_due_at": "2026-06-01T00:00:00Z",
    "decay_policy": "TIME_BASED",
    "half_life_days": 30
  },

  "evidence_refs": [
    {
      "type": "execution_log",
      "id": "exec_abc123",
      "tier": "TIER_0",
      "snapshot_digest": "sha256:...",
      "observed_at": "2026-04-08T10:25:00Z"
    }
  ],

  "applicability": {
    "domain": ["LLM_memory_system"],
    "constraints": [],
    "invalid_if": []
  },

  "relationships": {
    "primary_source": {
      "type": "conversation",
      "id": "conv_xyz"
    },
    "derived_from": [],
    "supersedes": [],
    "superseded_by": null,
    "conflict_group_id": "cg_001",
    "conflict_state": "NONE"
  }
}
```

## Required Metadata Themes

### Identity And Scope

Must identify:

- what the artifact is
- where it belongs
- whether it is workspace or global durable knowledge

### State And Visibility

Must define:

- whether the artifact is active
- whether it is searchable
- whether it is sanitized

### Validation And Confidence

Must define:

- when it was last validated
- who validated it
- what evidence tier supports it
- what confidence level it currently has

Important:

- `confidence` is a signal for ranking and governance
- it is not proof of truth

### Freshness

Durable memory must not behave as immortal truth.

It therefore needs:

- revalidation schedule
- decay policy

### Evidence Refs

Evidence refs must support audit, not just loose narrative claims.

They should point to:

- source type
- source identity
- evidence tier
- evidence snapshot or digest when possible

### Applicability

Durable knowledge must be bounded.

Applicability metadata prevents:

- over-reuse
- misuse outside intended context
- silent spread of stale assumptions

### Relationships

Durable artifacts live over time and may:

- supersede one another
- conflict with one another
- derive from earlier artifacts

The metadata header must support that lifecycle.

## Guidance On Usage Metrics

Usage metrics are useful but dangerous in the wrong place.

Recommended approach:

- keep usage rollups in sidecar telemetry
- avoid synchronous write-on-read updates on durable records

This prevents hot-record amplification.

## Guidance On Effective Confidence

The durable header should store base confidence only.

`effective_confidence` should be calculated dynamically during retrieval using:

- base confidence
- freshness
- verification tier
- artifact state

It should not be stored as a static canonical field.

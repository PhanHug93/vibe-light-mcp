# Validation Gate V1

Status: draft
Scope note: `V1` means temporarily locked for the current design scope.

## Purpose

`Validation Gate` is the mandatory enforcement point for any runtime-originated
artifact that attempts to become durable knowledge.

Without this gate, promotion rules remain advisory and will eventually be bypassed by:

- convenience writes
- manual shortcuts
- orchestration drift

## Hard Invariant

No runtime-originated artifact may be written into durable memory unless it passes the
validation gate.

This applies to:

- automated promotion
- reviewed promotion
- manual promotion
- admin override flows

The mode may differ, but the gate remains mandatory.

## Position In The Flow

```text
session_scratch / runtime artifact
-> extraction
-> promotion_candidate
-> validation gate
-> workspace_durable or global_durable
```

## What The Gate Must Check

The gate must enforce at least the following:

1. Rule 1: State Maturation
2. Rule 2: Prompt Artifact Grounding
3. Rule 3: Human Re-readability And Durable Value
4. Sanitization status
5. Evidence presence and tier quality
6. Confidence score threshold
7. Artifact-type-specific promotion requirements
8. Target-store-specific thresholds

## Gate Inputs

The gate receives:

- `promotion_candidate`
- target durable family (`workspace_durable` or `global_durable`)
- type definition / promotion policy
- gate config
- evidence refs
- confidence inputs

## Gate Outputs

The gate should not return only pass/fail.

Recommended outcome set:

- `REJECTED`
- `LOW_CONFIDENCE_STAGING`
- `REVIEW_REQUIRED`
- `PROMOTED_WORKSPACE`
- `PROMOTED_GLOBAL`

## Mandatory Decision Snapshot

Every gate run should emit an auditable decision record containing:

- gate run id
- artifact id
- decision
- timestamp
- checks performed
- thresholds applied
- prompt-artifact analysis
- reason codes

## Prompt Artifact Analysis

The gate must explicitly analyze prompt-derived risk.

Minimum required fields:

- whether prompt-derived content is present
- semantic overlap score
- whether external grounding exists
- resulting prompt-grounding decision

If prompt-derived content dominates and grounding is absent:

- `HARD REJECT`

## Confidence Use

`confidence_score` is a gate signal, not a truth claim.

The gate uses it to:

- threshold promotion
- prioritize review
- downgrade weak candidates

It does not replace:

- evidence
- verification tier
- human review when required

## Target-Specific Thresholding

The same artifact type may have different bars depending on durable target:

- `workspace_durable` may allow `EVIDENCE_BACKED`
- `global_durable` should generally require stronger confirmation

The gate must therefore evaluate:

- artifact type
- target durable store

together.

## Gate Modes

Recommended modes:

- `AUTO`
- `REVIEW`
- `HUMAN_APPROVED`
- `ADMIN_OVERRIDE`

Important:

- even `ADMIN_OVERRIDE` should leave a decision snapshot
- override does not mean bypass

## Failure Handling

If the gate rejects a candidate:

- the candidate must not enter durable memory
- the reason must remain auditable
- the artifact may remain staged temporarily if review is permitted

## Architectural Role

Validation Gate is the enforcement boundary between:

- runtime learning signals
- durable knowledge

That makes it the most important integrity control in the memory system.

# PATTERN V1

Status: draft

## Purpose

`PATTERN` stores a reusable solution shape that has worked across recurring situations.

It is not:

- a normative boundary like `RULE`
- a guiding stance like `PRINCIPLE`
- only a problem framing like `PROBLEM_TEMPLATE`
- an ordered multi-step procedure like `PLAYBOOK`

## Classification Rule

Use `PATTERN` when the artifact:

- captures a repeatable solution arrangement
- is grounded in multiple successful uses
- remains useful after the original task is gone
- does not depend on strict ordered execution steps

## Decision Test

```json
{
  "artifact_type": "PATTERN",
  "classification_test": {
    "all_must_be_true": [
      "The artifact describes a reusable solution shape, not only a preference.",
      "The artifact does not require strict ordered steps to remain valid.",
      "The artifact contains more than a recurring problem signature alone."
    ],
    "if_false": "classify_as_PRINCIPLE_or_PROBLEM_TEMPLATE_or_PLAYBOOK"
  }
}
```

## Content Instance Shape

```json
{
  "type_specific": {
    "pattern_kind": "RETRIEVAL_PATTERN",
    "solution_shape": [
      "bounded candidate selection",
      "hybrid ranking",
      "short-lived cache"
    ],
    "reuse_trigger": "Use when similar latency-sensitive retrieval requests recur and the validated operating range is known."
  }
}
```

## Field Semantics

- `pattern_kind`
  - subtype of pattern
  - suggested enums:
    - `RETRIEVAL_PATTERN`
    - `PROMOTION_PATTERN`
    - `ISOLATION_PATTERN`
    - `SANITIZATION_PATTERN`
    - `GOVERNANCE_PATTERN`
    - `CACHE_PATTERN`

- `solution_shape`
  - the reusable structural components of the pattern
  - should describe the arrangement, not the exact runtime transcript

- `reuse_trigger`
  - short statement explaining when the pattern is worth trying again
  - should remain less procedural than a playbook

## Type Definition / Promotion Policy

```json
{
  "artifact_type": "PATTERN",
  "promotion_bar": {
    "required": [
      "verification_tier meets minimum threshold for the target durable store",
      "canonical_statement is present and human-readable",
      "solution_shape is explicit",
      "applicability is explicit",
      "pattern is grounded by repeated or multi-source evidence",
      "prompt-derived evidence does not dominate without grounding",
      "sanitization_status is in the allowed durable set"
    ],
    "recommended": [
      "expected_outcomes documented",
      "failure_modes documented",
      "counterexamples documented",
      "operator_guidance included",
      "revalidation_triggers documented"
    ]
  }
}
```

## Machine-Readable Gate Config

```json
{
  "artifact_type": "PATTERN",
  "gate_config": {
    "workspace_durable": {
      "min_verification_tier": "EVIDENCE_BACKED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"]
    },
    "global_durable": {
      "min_verification_tier": "HUMAN_CONFIRMED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"]
    },
    "requires": {
      "canonical_statement": true,
      "human_readable": true,
      "solution_shape": true,
      "applicability": true,
      "grounded_evidence": true
    },
    "recommended": {
      "expected_outcomes": true,
      "failure_modes": true,
      "counterexamples": true,
      "operator_guidance": true,
      "revalidation_triggers": true
    }
  }
}
```

## Notes

- A `PATTERN` should explain a reusable arrangement, not a strict procedure.
- If ordered steps, entry conditions, and fallback paths become essential, the artifact is likely a `PLAYBOOK`.
- If only the recurring problem signature is durable, the artifact is likely a `PROBLEM_TEMPLATE`.

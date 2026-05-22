# PRINCIPLE V1

Status: draft

## Purpose

`PRINCIPLE` stores a durable guiding stance that helps humans and agents make better
decisions later.

It is not:

- a hard guard like `RULE`
- a local decision like `DECISION`
- a concrete solution shape like `PATTERN`
- an ordered procedure like `PLAYBOOK`

## Classification Rule

Use `PRINCIPLE` when the artifact:

- expresses a durable preference or bias across recurring situations
- remains useful after the original task is gone
- is grounded and contestable
- does not define a pass/fail compliance boundary

## Content Instance Shape

```json
{
  "type_specific": {
    "principle_kind": "OPERATING_PRINCIPLE",
    "guiding_preference": "Prefer bounded hybrid retrieval on latency-sensitive paths with explicit recall guardrails."
  }
}
```

## Type Definition / Promotion Policy

```json
{
  "artifact_type": "PRINCIPLE",
  "promotion_bar": {
    "required": [
      "verification_tier meets minimum threshold for the target durable store",
      "canonical_statement is present and human-readable",
      "applicability is explicit",
      "prompt-derived evidence does not dominate without grounding",
      "sanitization_status is in the allowed durable set"
    ],
    "recommended": [
      "tradeoffs documented",
      "counterexamples documented",
      "revalidation_triggers documented",
      "operator_guidance included"
    ]
  }
}
```

## Machine-Readable Gate Config

```json
{
  "artifact_type": "PRINCIPLE",
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
      "applicability": true,
      "grounded_evidence": true
    },
    "recommended": {
      "tradeoffs": true,
      "counterexamples": true,
      "revalidation_triggers": true,
      "operator_guidance": true
    }
  }
}
```

## Notes

- `tradeoffs` and `revalidation_triggers` belong to the common content schema, not to `type_specific`.
- `guiding_preference` should remain a stance, not a hard prohibition.
- If the statement can be checked as compliant or violated, it is likely a `RULE`, not a `PRINCIPLE`.

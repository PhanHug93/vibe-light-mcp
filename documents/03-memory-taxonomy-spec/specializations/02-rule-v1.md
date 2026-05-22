# RULE V1

Status: draft

## Purpose

`RULE` stores a durable guardrail or invariant that can be enforced.

It exists to protect:

- durable memory integrity
- retrieval boundaries
- isolation safety
- sanitization guarantees
- governance flow correctness

## Classification Rule

Use `RULE` when the artifact:

- defines a normative `MUST` or `MUST_NOT`
- has a machine-checkable or at least operationally checkable violation condition
- has at least one enforcement surface

If these conditions are not met, it is likely a `PRINCIPLE` or `PATTERN`.

## Content Instance Shape

```json
{
  "type_specific": {
    "rule_kind": "RETRIEVAL_BOUNDARY_RULE",
    "rule_mode": "BOUNDARY_GUARD",
    "rule_stance": "MUST_NOT",
    "enforcement_level": "HARD",
    "enforcement_surface": [
      "retrieval_planner",
      "validation_gate"
    ],
    "allowed_exceptions": [
      "DEBUG_ADMIN_MODE"
    ],
    "violation_condition": {
      "condition_language": "rule-condition/v1",
      "subject": "retrieval_event",
      "when_all": [
        {
          "field": "path_kind",
          "op": "EQ",
          "value": "HUMAN_READABLE"
        },
        {
          "field": "source_store",
          "op": "IN",
          "value": ["gateway_ops_store"]
        }
      ],
      "unless_any": [
        {
          "field": "debug_mode",
          "op": "EQ",
          "value": true
        },
        {
          "field": "admin_override",
          "op": "EQ",
          "value": true
        }
      ]
    },
    "violation_summary": "Gateway operational artifacts appear in normal human-readable retrieval."
  }
}
```

## Decision Test

```json
{
  "artifact_type": "RULE",
  "classification_test": {
    "all_must_be_true": [
      "A concrete event or state can be marked compliant or violated.",
      "At least one enforcement surface exists.",
      "The statement is normative as MUST or MUST_NOT, not merely a preference."
    ],
    "if_false": "classify_as_PRINCIPLE_or_PATTERN"
  }
}
```

## Type Definition / Promotion Policy

```json
{
  "artifact_type": "RULE",
  "promotion_bar": {
    "required": [
      "verification_tier meets minimum threshold for the target durable store",
      "canonical_statement is precise and human-readable",
      "rule_mode is defined",
      "rule_stance is MUST or MUST_NOT",
      "violation_condition is machine-checkable",
      "enforcement_surface is defined",
      "prompt-derived evidence does not dominate without grounding",
      "sanitization_status is in the allowed durable set"
    ],
    "recommended": [
      "allowed_exceptions documented",
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
  "artifact_type": "RULE",
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
      "rule_mode": true,
      "rule_stance": true,
      "machine_checkable_violation_condition": true,
      "enforcement_surface": true,
      "grounded_evidence": true
    },
    "recommended": {
      "allowed_exceptions": true,
      "failure_modes": true,
      "counterexamples": true,
      "operator_guidance": true,
      "revalidation_triggers": true
    }
  }
}
```

## Notes

- If a statement cannot define a violation condition, it should not be promoted as `RULE`.
- `RULE` should encode boundaries and invariants, not merely strong opinions.

# PROBLEM_TEMPLATE V1

Status: draft

## Purpose

`PROBLEM_TEMPLATE` stores a durable recurring problem signature that has matured beyond
 one-off task state.

It exists to capture:

- recurring intent shape
- recurring constraints
- recurring failure or pressure signals
- a reusable framing of the problem space

It is not:

- a preference like `PRINCIPLE`
- an enforceable boundary like `RULE`
- a reusable solution shape like `PATTERN`
- an ordered execution procedure like `PLAYBOOK`

## Why This Type Exists

Some artifacts begin life as runtime state, for example:

- normalized task state
- repeated optimization framing
- recurring diagnostic framing

If they recur, are verified, and are rewritten into a context-independent form, they
stop being mere state. They become reusable problem framing.

This type exists to model that maturation explicitly.

## Classification Rule

Use `PROBLEM_TEMPLATE` when the artifact:

- captures a recurring problem signature rather than a specific instance
- remains useful after the originating task is gone
- is more than a temporary task framing
- does not yet encode the solution shape strongly enough to be a `PATTERN`

## Decision Test

```json
{
  "artifact_type": "PROBLEM_TEMPLATE",
  "classification_test": {
    "all_must_be_true": [
      "The artifact describes a recurring problem signature, not only one task instance.",
      "The artifact remains useful even when the original session context is removed.",
      "The artifact contains more than a preference but less than a reusable solution arrangement."
    ],
    "if_false": "classify_as_STATE_or_PRINCIPLE_or_PATTERN_or_PLAYBOOK"
  }
}
```

## Content Instance Shape

```json
{
  "type_specific": {
    "template_kind": "OPTIMIZATION_PROBLEM_TEMPLATE",
    "problem_signature": {
      "intent": "optimize RAG latency",
      "constraints": [
        "<200ms",
        "top_k <= 5"
      ],
      "signals": [
        "retrieval fan-out too broad",
        "repeated similar queries",
        "latency target at risk"
      ]
    },
    "problem_goal": "Reduce retrieval latency without dropping below the accepted recall threshold.",
    "reuse_trigger": "Use when the request pattern matches a recurring latency-sensitive retrieval optimization problem."
  }
}
```

## Field Semantics

- `template_kind`
  - subtype of problem template
  - suggested enums:
    - `OPTIMIZATION_PROBLEM_TEMPLATE`
    - `RELIABILITY_PROBLEM_TEMPLATE`
    - `GOVERNANCE_PROBLEM_TEMPLATE`
    - `ISOLATION_PROBLEM_TEMPLATE`
    - `SANITIZATION_PROBLEM_TEMPLATE`
    - `RETRIEVAL_PROBLEM_TEMPLATE`

- `problem_signature`
  - reusable framing of the problem itself
  - should capture recurring intent, constraints, and diagnostic cues
  - should not encode a full solution shape

- `problem_goal`
  - short statement of what success means inside this problem class

- `reuse_trigger`
  - short statement of when the template should be considered again

## Promotion Bar

Problem templates are easy to over-promote from runtime state. Their promotion bar
should therefore be stricter than ordinary state preservation.

## Type Definition / Promotion Policy

```json
{
  "artifact_type": "PROBLEM_TEMPLATE",
  "promotion_bar": {
    "required": [
      "verification_tier meets minimum threshold for the target durable store",
      "canonical_statement is present and human-readable",
      "problem_signature is explicit",
      "problem signature is recurrence-backed rather than one-shot",
      "applicability is explicit",
      "prompt-derived evidence does not dominate without grounding",
      "sanitization_status is in the allowed durable set"
    ],
    "recommended": [
      "assumptions documented",
      "failure_modes documented",
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
  "artifact_type": "PROBLEM_TEMPLATE",
  "gate_config": {
    "workspace_durable": {
      "min_verification_tier": "EVIDENCE_BACKED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"],
      "min_occurrence_count": 2
    },
    "global_durable": {
      "min_verification_tier": "HUMAN_CONFIRMED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"],
      "min_occurrence_count": 3
    },
    "requires": {
      "canonical_statement": true,
      "human_readable": true,
      "problem_signature": true,
      "problem_goal": true,
      "applicability": true,
      "grounded_evidence": true,
      "recurrence_backed": true
    },
    "recommended": {
      "assumptions": true,
      "failure_modes": true,
      "counterexamples": true,
      "revalidation_triggers": true,
      "operator_guidance": true
    }
  }
}
```

## Distinguishing `PROBLEM_TEMPLATE` From Nearby Types

- vs `PRINCIPLE`
  - `PRINCIPLE` expresses a guiding stance
  - `PROBLEM_TEMPLATE` expresses a recurring problem framing

- vs `PATTERN`
  - `PATTERN` expresses a reusable solution arrangement
  - `PROBLEM_TEMPLATE` expresses the recurring problem shape before or apart from the solution

- vs `PLAYBOOK`
  - `PLAYBOOK` includes ordered execution steps, fallback paths, and exit conditions
  - `PROBLEM_TEMPLATE` does not

## Notes

- `normalized_task_state` starts as state, not knowledge.
- Repetition alone is not enough. The artifact must also be verified and rewritten into a stable, reusable framing.
- If the artifact mostly describes what to do, not what problem shape recurs, it is likely a `PATTERN` or `PLAYBOOK`.

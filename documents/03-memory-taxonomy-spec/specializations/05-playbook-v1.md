# PLAYBOOK V1

Status: draft

## Purpose

`PLAYBOOK` stores a durable, reusable execution approach for a recurring class of
problems.

It exists to capture:

- entry conditions
- ordered or semi-ordered steps
- fallback paths
- exit conditions
- operational guardrails during execution

It is the strongest and most operationally prescriptive specialization in this layer.

It is not:

- a guiding stance like `PRINCIPLE`
- a hard boundary like `RULE`
- only a reusable arrangement like `PATTERN`
- only a recurring problem signature like `PROBLEM_TEMPLATE`

## Why This Type Exists

Some knowledge matures beyond:

- "what kind of problem is this?" (`PROBLEM_TEMPLATE`)
- "what solution shape tends to work?" (`PATTERN`)

At that stage, the system has enough validated structure to say:

- if this problem class appears
- and these entry conditions hold
- then execute roughly this sequence
- with these fallbacks and stop conditions

That is a `PLAYBOOK`.

## Classification Rule

Use `PLAYBOOK` when the artifact:

- applies to a recurring problem class
- encodes an execution flow, not only a solution shape
- includes explicit entry conditions and exit conditions
- benefits from at least partially ordered steps
- would lose important meaning if reduced to only a `PATTERN`

## Decision Test

```json
{
  "artifact_type": "PLAYBOOK",
  "classification_test": {
    "all_must_be_true": [
      "The artifact contains an execution flow, not only a reusable arrangement.",
      "The artifact defines entry conditions and exit conditions.",
      "The artifact would become materially weaker if step order or fallback logic were removed."
    ],
    "if_false": "classify_as_PATTERN_or_PROBLEM_TEMPLATE_or_PRINCIPLE"
  }
}
```

## Content Instance Shape

```json
{
  "type_specific": {
    "playbook_kind": "RETRIEVAL_OPTIMIZATION_PLAYBOOK",
    "entry_conditions": [
      "The request path is latency-sensitive.",
      "A validated recall threshold exists.",
      "Source freshness is observable or bounded."
    ],
    "steps": [
      "Normalize the request and identify whether it belongs to a recurring latency-sensitive retrieval class.",
      "Apply bounded candidate selection before broad retrieval fan-out.",
      "Use hybrid ranking within the validated operating range.",
      "Enable short-lived cache only if freshness constraints are satisfied.",
      "Monitor recall misses and latency against the defined threshold."
    ],
    "fallbacks": [
      "Disable cache if freshness cannot be guaranteed.",
      "Temporarily increase retrieval breadth if recall misses exceed the accepted threshold."
    ],
    "exit_conditions": [
      "Latency target is met without unacceptable recall loss.",
      "The request leaves the validated operating range and should escalate to a broader strategy."
    ]
  }
}
```

## Field Semantics

- `playbook_kind`
  - subtype of playbook
  - suggested enums:
    - `RETRIEVAL_OPTIMIZATION_PLAYBOOK`
    - `PROMOTION_GOVERNANCE_PLAYBOOK`
    - `ISOLATION_RESPONSE_PLAYBOOK`
    - `SANITIZATION_RESPONSE_PLAYBOOK`
    - `CACHE_CONTROL_PLAYBOOK`

- `entry_conditions`
  - preconditions required before the playbook should be applied

- `steps`
  - ordered or semi-ordered actions that define the playbook
  - should stay concise and operational

- `fallbacks`
  - what to do when the main flow no longer holds or quality drops

- `exit_conditions`
  - when the playbook is considered complete or no longer applicable

## Promotion Bar

Playbooks are powerful but risky. If promoted too early, they turn local tactics into
over-generalized operating procedures.

Their promotion bar should therefore be the strictest among the currently defined
specializations.

## Type Definition / Promotion Policy

```json
{
  "artifact_type": "PLAYBOOK",
  "promotion_bar": {
    "required": [
      "verification_tier meets minimum threshold for the target durable store",
      "canonical_statement is present and human-readable",
      "entry_conditions are explicit",
      "steps are explicit and operationally meaningful",
      "fallbacks are documented when the execution path can degrade",
      "exit_conditions are explicit",
      "playbook is grounded by repeated successful use or equivalent strong evidence",
      "prompt-derived evidence does not dominate without grounding",
      "sanitization_status is in the allowed durable set"
    ],
    "recommended": [
      "assumptions documented",
      "tradeoffs documented",
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
  "artifact_type": "PLAYBOOK",
  "gate_config": {
    "workspace_durable": {
      "min_verification_tier": "HUMAN_CONFIRMED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"],
      "min_occurrence_count": 3
    },
    "global_durable": {
      "min_verification_tier": "HUMAN_CONFIRMED",
      "allowed_sanitization_statuses": ["SANITIZED", "REDACTED"],
      "min_occurrence_count": 5
    },
    "requires": {
      "canonical_statement": true,
      "human_readable": true,
      "entry_conditions": true,
      "steps": true,
      "exit_conditions": true,
      "grounded_evidence": true,
      "recurrence_backed": true
    },
    "recommended": {
      "assumptions": true,
      "tradeoffs": true,
      "failure_modes": true,
      "counterexamples": true,
      "operator_guidance": true,
      "revalidation_triggers": true
    }
  }
}
```

## Distinguishing `PLAYBOOK` From Nearby Types

- vs `PATTERN`
  - `PATTERN` gives a reusable arrangement
  - `PLAYBOOK` gives a reusable execution flow

- vs `PROBLEM_TEMPLATE`
  - `PROBLEM_TEMPLATE` captures recurring problem framing
  - `PLAYBOOK` captures how to respond once that problem class is recognized

- vs `RULE`
  - `RULE` defines what must or must not happen
  - `PLAYBOOK` defines a recommended operational path under given conditions

- vs `PRINCIPLE`
  - `PRINCIPLE` expresses a guiding stance
  - `PLAYBOOK` expresses a practical approach with steps and stop conditions

## Notes

- A playbook should remain reusable, not overfit to a single incident.
- If the artifact only explains a structural pattern and not an execution path, it should stay a `PATTERN`.
- If the artifact only captures recurring framing and constraints, it should stay a `PROBLEM_TEMPLATE`.
- Playbooks should be promoted cautiously because they influence operator and agent behavior more directly than other specialization types.

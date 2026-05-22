# Three Core Rules V1

Status: draft
Scope note: `V1` means temporarily locked for the current design scope.

## Purpose

This document defines the three normative rules that protect durable memory quality in
the dual-purpose MCP architecture.

These rules are not optional editorial guidance. They are intended to shape:

- promotion policy
- validation gate behavior
- durable memory acceptance criteria
- artifact rewriting and review

## Rule 1: State Maturation

State is not knowledge.

Only when a state:

- recurs
- is verified
- is rephrased into a stable and reusable form

may it be promoted toward durable memory.

### Interpretation

- `normalized_task_state` starts as runtime state
- `session_scratch` is a promotion source, not durable knowledge
- repetition is necessary but not sufficient
- the artifact must also be rewritten into a context-independent form

### Consequence

The valid maturation path is:

```text
runtime state
-> extraction
-> promotion_candidate
-> validation gate
-> durable memory
```

Direct promotion from scratch or task state is forbidden.

## Rule 2: Prompt Artifact Grounding

Prompt artifacts are secondary sources only.

They:

- must not be used as primary evidence
- must not dominate the semantic substance of a promoted artifact

Every extraction from a prompt artifact must have supporting evidence from Tier 0 or
Tier 1.

If not, the artifact must be:

- rejected
- or held below the durable promotion threshold

### Hard Guard

If:

- artifact content has high semantic overlap with prompt content
- and no external grounding is present

then:

- `HARD REJECT`

### Interpretation

Prompt artifacts may help with:

- framing
- intent packaging
- constraint grouping

Prompt artifacts may not act as:

- ground truth
- primary evidence
- direct durable knowledge source

## Rule 3: Human Re-readability And Durable Value

Durable memory only stores artifacts that humans can:

- understand
- verify
- debate
- reuse

Durable memory is not a place to store things that merely sound intelligent.

It is a place to store artifacts that are:

- correct according to current evidence
- and still useful when read again later

### Interpretation

The following do not qualify as durable knowledge by default:

- compiled prompts
- runtime traces
- session notes
- one-shot synthesis without grounding
- machine-oriented payload internals

### Important Note

Human re-readability is a necessary condition, not a sufficient one.

An artifact may still be rejected if it is:

- too narrow
- not reusable
- weakly grounded
- stale or highly volatile

## System-Level Consequences

These three rules imply:

1. `session_scratch` is runtime working memory only
2. `promotion_candidate` is the only runtime-originated artifact eligible for durable promotion
3. `compiled_prompt_input` is never written directly to durable memory
4. durable memory must remain curated, auditable, and low-noise

## Enforcement Implication

These rules must be enforced by `Validation Gate V1`, not only documented.

If they are bypassable, the architecture will drift toward:

- memory pollution
- self-referential learning
- stale or misleading durable knowledge

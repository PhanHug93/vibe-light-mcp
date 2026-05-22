# Core Data Flows

Status: draft

## Flow 1: Human-Readable Recall

```text
User / Agent asks for old context
-> Human retrieval tool
-> Search durable workspace/global memory
-> Return readable result
```

Purpose:
- recover previously stored knowledge for human or agent interpretation

Expected output:
- readable summaries
- memory hits with provenance
- explanations or references

This flow must not depend on runtime payload cache by default.

## Flow 2: Executor Payload Preparation

```text
User input or task request
-> prepare_llm_payload
-> normalize intent
-> inspect workspace facts
-> retrieve session + durable evidence
-> rank and compress
-> emit structured executor payload
```

Purpose:
- reduce raw-context volume before the next LLM call

Expected output:
- structured JSON contract
- selected context blocks
- compiled executor input
- budget and trace metadata

This flow is operational, not merely diagnostic.

## Flow 3: Session Working Memory

```text
Agent produces intermediate context
-> session-scoped write
-> session scratch
-> later prepare_llm_payload reads it back
```

Purpose:
- support multi-step and multi-agent runtime continuity without immediately polluting durable memory

This flow should be isolated by agent/session policy and have short retention.

## Flow 4: Promotion

```text
Candidate runtime artifact
-> hard filter
-> evidence consolidation
-> verification tiering
-> scoring
-> rewrite
-> approval
-> workspace/global durable persist
```

Purpose:
- convert verified, reusable, sanitized runtime outputs into durable knowledge

Promotion is the system's learning flow. It must be slower and stricter than runtime preparation.

## Flow Interaction Rules

1. Flow 2 may read outputs from Flow 3 and durable memory.
2. Flow 1 does not read Flow 2 artifacts by default.
3. Flow 4 is the only path that moves gateway/runtime artifacts into durable memory.
4. A compiled payload must not automatically re-enter Flow 2 as durable evidence.

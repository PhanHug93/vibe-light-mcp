# Architectural Risks And Constraints

Status: draft

## Primary Risks

### 1. Memory Pollution

If executor artifacts are stored like durable knowledge, long-term recall quality will degrade.

### 2. Self-Amplifying Retrieval

If the gateway retrieves previous compiled payloads as evidence, the system can recursively
amplify its own prior compression errors.

### 3. False Isolation Expectations

If users assume session scope means total isolation, but workspace durable memory is shared,
they may misinterpret system behavior.

### 4. Contract Drift

If executor payload fields change without a versioned stable core, downstream executors will break.

### 5. Over-Compression

If the gateway optimizes too aggressively for token savings, recall quality will fall below trust threshold.

### 6. Under-Compression

If the gateway remains too conservative, agents will see little benefit and will keep using heavier legacy flows.

## Constraints

1. One MCP process must support both human-facing and executor-facing use cases.
2. The human-readable memory product must remain understandable.
3. The gateway product must remain operationally stable.
4. Promotion must stay conservative enough to protect durable memory quality.
5. The system must be designed with at least 4 concurrent agents in mind.

## Architectural Guardrails

1. Runtime cache is not durable memory.
2. Promotion is mandatory for durable learning.
3. Durable memory should only store rewritten and sanitized artifacts.
4. Debug data must be separable from the operational payload core.
5. Retrieval topology must be explicit per plane and per tool type.

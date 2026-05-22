# Products And Boundaries

Status: draft

## Product 1: Human-Readable Memory

Purpose:
- Store and retrieve decisions, patterns, bug fixes, summaries, and reusable knowledge.

Characteristics:
- Human-readable output.
- Searchable.
- Durable or semi-durable retention.
- Optimized for comprehension and reuse, not raw execution speed.

Primary consumers:
- Human operator
- Interactive coding agent
- Reviewer or planner agents

## Product 2: Executor-Facing Gateway

Purpose:
- Prepare compact, structured, low-noise payloads for the next LLM call.

Characteristics:
- JSON-first output.
- Machine-oriented.
- Budget-aware.
- Optimized for recall quality first, then token savings, then latency.

Primary consumers:
- Executor runtime
- Agent orchestration loop

## Product 3: Learning Mechanism

Purpose:
- Decide what runtime output is worth promoting into durable memory.

Characteristics:
- Policy-driven.
- Conservative by default.
- Requires filter, scoring, rewrite, and optional approval.

## Boundary Rules

1. Human-readable memory is not the same thing as runtime gateway state.
2. Gateway payloads are not durable knowledge.
3. Promotion is required before runtime artifacts become durable memory.
4. Human-facing tools must not expose runtime payload cache by default.
5. Executor-facing tools may read durable memory, but durable memory must not ingest executor artifacts automatically.

## Architectural Consequence

This MCP is not a single-memory system anymore. It is a shared platform with at least
two operational planes and one governance plane.

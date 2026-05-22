# Memory Planes And Governance

Status: draft

## Plane 1: Human Memory Plane

Purpose:
- preserve durable knowledge that humans and agents can read, understand, and reuse

Contains:
- workspace durable memory
- global durable memory
- promoted summaries, rules, patterns, decisions

Properties:
- searchable
- human-readable
- retention is medium to long
- cannot ingest runtime gateway artifacts directly

## Plane 2: Executor Gateway Plane

Purpose:
- compile the minimum viable context package for the next LLM call

Contains:
- session scratch
- short-lived payload cache
- normalized task state
- selected evidence snapshot
- compiled prompt input

Properties:
- machine-oriented
- budget-aware
- ephemeral by default
- optimized for runtime usefulness, not human readability

## Plane 3: Promotion And Governance Plane

Purpose:
- decide what, if anything, should move from runtime state into durable knowledge

Contains:
- hard filter policy
- scoring policy
- rewrite policy
- approval rules
- revalidation and rollback governance

Properties:
- conservative
- policy-driven
- required for durable writes from runtime-originated artifacts

## Boundary Rules

1. Human tools read the Human Memory Plane by default.
2. Gateway tools read Executor Gateway Plane plus durable memory read-through.
3. Gateway tools do not write durable memory by default.
4. Promotion is the only approved bridge from runtime artifacts to durable memory.
5. Debug visibility into runtime artifacts should be explicit, not default.

## Architectural Consequence

Even if all planes sit behind one MCP process, they must behave as different products
with different contracts, retention rules, and governance controls.

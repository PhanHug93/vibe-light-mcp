# 01. System Vision & Scope

Status: draft
Owner: architecture
Last updated: 2026-04-08

## Purpose

This folder defines the system vision and scope for the next evolution of this MCP
server. It establishes the architectural intent before deeper specs such as memory
taxonomy, retrieval topology, retention policy, and promotion workflow.

The target direction is explicit:

- Keep the original human-readable memory product.
- Add an executor-facing gateway product for LLM payload preparation.
- Treat promotion as the learning mechanism between runtime artifacts and durable knowledge.

## Decision Summary

The following decisions are currently locked for `01`:

1. The current MCP is a `tool-level gateway`, with a roadmap toward a `transport-level gateway`.
2. Priority order is:
   - `recall quality`
   - `token saving`
   - `latency`
3. `workspace durable memory` is `shared per project`, not a general team-wide memory.
4. Gateway output is an `operational artifact with SLA` for its stable core fields, while debug/trace data remains best-effort.

## Folder Structure

- [01-vision-and-scope.md](./01-vision-and-scope.md)
- [02-products-and-boundaries.md](./02-products-and-boundaries.md)
- [03-key-architecture-decisions.md](./03-key-architecture-decisions.md)
- [04-success-metrics-and-failure-modes.md](./04-success-metrics-and-failure-modes.md)

## Review Intent

This folder should answer four questions:

1. What system are we trying to build?
2. What is explicitly in scope and out of scope?
3. What architectural decisions are already locked?
4. How will we judge whether the direction is working?

## Next Documents After Approval

Once this folder is approved, the next recommended specs are:

1. `02-target-architecture-v2`
2. `03-memory-taxonomy-spec`
3. `04-retrieval-topology-and-isolation`
4. `05-executor-payload-contract`

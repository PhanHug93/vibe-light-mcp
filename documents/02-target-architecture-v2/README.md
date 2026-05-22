# 02. Target Architecture V2

Status: draft
Owner: architecture
Last updated: 2026-04-08

## Purpose

This folder defines the target architecture for the MCP server after it evolves from a
memory-centric RAG sidecar into a dual-purpose platform:

- human-readable long-term context system
- executor-facing gateway for compact LLM payload preparation

This architecture is designed to preserve the original value of durable memory while
adding a controlled runtime plane for token-efficient executor workflows.

## What This Folder Covers

1. The architectural shape of the system
2. Memory planes and their responsibilities
3. Data flow between user input, gateway compilation, memory, and promotion
4. Deployment model boundaries
5. Risks introduced by the dual-purpose design

## Folder Structure

- [01-architecture-overview.md](./01-architecture-overview.md)
- [02-memory-planes-and-governance.md](./02-memory-planes-and-governance.md)
- [03-core-data-flows.md](./03-core-data-flows.md)
- [04-deployment-modes-and-roadmap.md](./04-deployment-modes-and-roadmap.md)
- [05-architectural-risks-and-constraints.md](./05-architectural-risks-and-constraints.md)

## Architecture Summary

The system is no longer a single memory service. The target shape is a three-plane
architecture:

1. Human Memory Plane
2. Executor Gateway Plane
3. Promotion And Governance Plane

Each plane may share infrastructure, but they must not share the same retrieval,
retention, or persistence semantics.

## Review Goal

This folder should answer:

1. What components make up the target system?
2. How do the data planes interact?
3. Where are the hard boundaries?
4. What architectural risks appear once memory and gateway coexist?

## Next Specs After Approval

After `02` is approved, the next recommended documents are:

1. `03-memory-taxonomy-spec`
2. `04-retrieval-topology-and-isolation`
3. `05-executor-payload-contract`
4. `08-retention-policy-spec`

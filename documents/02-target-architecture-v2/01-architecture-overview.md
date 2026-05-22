# Architecture Overview

Status: draft

## Intent

The target system must support two different operating modes without collapsing them
into one ambiguous memory behavior:

- Human-readable recall
- Executor-facing payload compilation

To do this safely, the architecture must separate runtime artifacts from durable
knowledge, even when they share the same MCP server and storage infrastructure.

## Target Shape

```text
Human / Agent
   |
   | human-readable retrieval
   v
[Human Memory Plane]
   ^
   | promoted knowledge only
   |
[Promotion And Governance Plane]
   |
   | policy-controlled promotion
   v
[Executor Gateway Plane]
   |
   | compact compiled payload
   v
Executor / LLM Runtime
```

## Architectural Statement

This MCP becomes a shared platform with:

1. A readable memory product
2. A machine-oriented gateway product
3. A governance layer that controls what the system learns over time

## Hard Separation Requirement

The system must not treat these artifacts as equivalent:

- raw user input
- session scratch state
- compiled payloads
- durable workspace knowledge
- durable global knowledge

If these categories are mixed too early, retrieval quality and trust will degrade.

## Design Bias

The architecture is intentionally biased toward:

1. recall quality
2. memory integrity
3. controlled learning
4. token efficiency
5. latency optimization

This means the gateway is not allowed to maximize compression at the cost of memory
pollution or recall collapse.

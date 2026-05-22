# Vision And Scope

Status: draft

## Vision

This MCP server will evolve into a dual-purpose context platform with two concurrent
products:

- A human-readable memory system for long-term context retrieval.
- An executor-facing gateway that compiles compact LLM-ready payloads.

The system must support both without allowing runtime payload artifacts to pollute
durable memory.

## System Goals

1. Reduce the token volume agents send into the next LLM call.
2. Reduce the time agents spend processing raw user input and oversized tool output.
3. Preserve durable context that remains understandable by humans and reusable by agents.
4. Support safe multi-agent operation on a shared MCP process.
5. Allow the system to improve over time through controlled promotion, not uncontrolled accumulation.

## In Scope

- Long-term memory at workspace and global levels.
- Session-scoped runtime memory for multi-agent usage.
- A gateway flow that compiles structured JSON payloads for executor use.
- Policies for retention, promotion, sanitization, and isolation.
- Observability for token savings, latency, recall, and contamination.

## Out Of Scope

- Full network-layer interception of all user input before it reaches any model client.
- Replacing the entire agent orchestration layer.
- Automatic durable learning from all runtime artifacts.
- Treating compiled payloads as durable knowledge by default.

## Core Principles

- Default ephemeral, selective durable.
- Human-readable retrieval and executor payload preparation must not share the same semantics.
- Promotion is the only approved learning path into durable memory.
- Durable knowledge requires provenance, verification, and sanitization.

## System Shape

The intended system shape is:

- Memory product for humans and agents who need readable recall.
- Gateway product for executors who need compact, machine-oriented input.
- Promotion layer that bridges runtime signals into approved durable knowledge.

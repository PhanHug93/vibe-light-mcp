# Deployment Modes And Roadmap

Status: draft

## Current Deployment Reality

The MCP currently operates as a tool-level gateway:

- the agent receives user input
- the agent calls MCP tools
- `prepare_llm_payload` prepares context for the next model step

This is useful and deployable, but not yet a transport-enforced gateway.

## Current Strength

Tool-level deployment is enough to validate:

- executor payload contract
- memory plane separation
- session isolation model
- retention and promotion rules

## Current Limitation

Because this is not yet transport-level:

- raw user input may reach the agent before MCP compilation
- agents may still bypass the gateway path
- policy enforcement depends partly on orchestration discipline

## Roadmap Target

Longer term, the architecture should support a transport-level gateway mode:

```text
User input
-> gateway orchestration layer
-> MCP payload preparation
-> LLM call
-> optional promotion candidate extraction
```

## Why The Roadmap Matters

If the tool-level contract is unstable, moving to transport-level only hardens the wrong behavior.
Therefore:

1. stabilize contract first
2. stabilize memory boundaries second
3. validate promotion governance third
4. harden transport integration later

## Architectural Position

The current system should be described honestly as:

- a productionizable tool-level gateway
- with a transport-level gateway roadmap

This avoids overstating current guarantees while preserving the long-term direction.

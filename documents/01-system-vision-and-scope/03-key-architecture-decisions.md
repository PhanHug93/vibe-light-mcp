# Key Architecture Decisions

Status: draft

## Decision 1: Gateway Level

Current decision:
- The MCP is a `tool-level gateway` in the current phase.
- The roadmap target is a `transport-level gateway`.

Rationale:
- Tool-level integration is deployable now and compatible with existing MCP usage.
- It is sufficient for validating the gateway contract, memory model, and promotion design.
- Transport-level enforcement should come later, once the contract and governance rules are stable.

Consequence:
- Raw user input may still reach the agent before the MCP gateway is called.
- Token savings and consistency are improved, but not fully enforced at infrastructure level.

## Decision 2: Priority Order

Current decision:
1. Recall quality
2. Token saving
3. Latency

Rationale:
- If the gateway drops important context, agents will stop trusting it.
- Compression only matters if the selected context remains correct and sufficient.
- Latency optimization should follow a stable retrieval and payload contract.

Consequence:
- Some gateway outputs may be slightly larger or slower at first.
- The system is intentionally biased toward correctness over aggressive compression.

## Decision 3: Meaning Of Workspace Durable Memory

Current decision:
- `workspace durable memory` is `shared per project`.

It is not:
- an organization-wide memory
- a generic team memory spanning multiple unrelated codebases

Rationale:
- Most workspace knowledge depends on repo-specific conventions, architecture, and constraints.
- Treating workspace memory as broader team memory would increase cross-project contamination risk.

Consequence:
- Reuse inside a project is encouraged.
- Cross-project reuse should happen only through `global durable memory` after stronger promotion.

## Decision 4: Nature Of Gateway Output

Current decision:
- Gateway output is an `operational artifact with SLA` for its stable core.
- Trace and debug fields are best-effort diagnostics, not part of the strict SLA surface.

Stable core should include:
- schema version
- task
- scope
- budget
- selected context blocks
- compiled executor input

Best-effort diagnostics may include:
- ranking trace
- retrieval counters
- drop reasons
- internal scoring notes

Rationale:
- Executors need a stable contract.
- The system still needs room to evolve diagnostics without breaking downstream consumers.

Consequence:
- The payload schema must be versioned.
- Backward compatibility matters for core fields.

# Success Metrics And Failure Modes

Status: draft

## Success Metrics

System-level success should be measured across four axes:

1. Recall quality
- Important context is not routinely omitted from gateway payloads.

2. Token efficiency
- The compiled payload is materially smaller than the previous raw context path.

3. Operational responsiveness
- Gateway preparation time remains acceptable for interactive agent workflows.

4. Knowledge quality
- Durable memory remains useful, readable, and resistant to contamination.

## Example Metrics

- median and p95 context tokens before vs after gateway compilation
- median and p95 gateway preparation latency
- recall miss rate on representative tasks
- durable memory reuse rate
- promotion precision
- contamination or rollback rate
- concurrent performance with at least 4 active agents

## Failure Modes To Avoid

1. Gateway artifacts pollute durable memory.
2. Human-readable retrieval returns machine-oriented JSON or runtime traces.
3. Session-local context leaks across agents.
4. Incorrect or weakly verified knowledge is promoted and then repeatedly reused.
5. Agents bypass the gateway and revert to heavy raw-context flows.
6. The gateway becomes so conservative that token savings are negligible.
7. The gateway becomes so aggressive that recall quality drops below trust threshold.

## Acceptance Criteria For This Section

- The system has explicit metrics for recall, token savings, latency, and contamination.
- Failure modes are named early enough to influence later specs.
- The 4-agent target is treated as an operational requirement, not just a thread-pool setting.

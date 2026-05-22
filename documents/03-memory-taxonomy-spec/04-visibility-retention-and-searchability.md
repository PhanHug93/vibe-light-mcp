# Visibility Retention And Searchability

Status: draft

## Behavioral Matrix

| Artifact Family | Searchable | Human Visible | Gateway Readable | Promotion Eligible | Default Retention |
|---|---|---|---|---|---|
| `workspace_durable` | Yes | Yes | Yes | Already durable | Medium/Long |
| `global_durable` | Yes | Yes | Yes | Already durable | Longest |
| `session_scratch` | No by default | No by default | Yes | No direct promotion; extraction source only | Short |
| `payload_metadata_cache` | No | Restricted diagnostics only | Yes | No by default | Very short |
| `source_manifest` | No | No | Yes | No | Very short |
| `retry_capsule` | No | No | Limited runtime only | No | Minimal |
| `promotion_candidate` | No | Review/Admin only | Governance only | Under evaluation | Short/Medium |

## Visibility Rules

### Human Tools

By default, human-facing retrieval should only expose:

- `workspace_durable`
- `global_durable`

It should not expose:

- session scratch
- payload content
- raw runtime traces

### Gateway Tools

Gateway flows may read:

- `session_scratch`
- `workspace_durable`
- `global_durable`
- `payload_metadata_cache` when useful operationally
- `source_manifest` when deterministic rebuild or lineage inspection is required

Gateway flows should not use `retry_capsule` as standard retrieval evidence.

### Debug Visibility

Debug mode should expose only opaque diagnostics such as:

- current stage
- accessed sources
- counts
- cache hit or miss
- block selected or dropped

Debug mode should not expose:

- raw user content
- compiled payload content
- session scratch content
- selected block full text

## Retention Guidance

- `retry_capsule`: shortest TTL
- `payload_metadata_cache`: very short TTL
- `source_manifest`: very short TTL
- `session_scratch`: short TTL
- `promotion_candidate`: short to medium TTL
- `workspace_durable`: long TTL
- `global_durable`: longest TTL

## Searchability Rule

Only durable memory families should participate in normal human-readable recall.

This is the simplest and safest baseline. Any exception should be explicit and
administrative, not default product behavior.

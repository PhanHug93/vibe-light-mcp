# Artifact Families

Status: draft

## 1. `workspace_durable`

Purpose:
- store project-specific durable knowledge

Examples:
- confirmed decision
- reusable fix pattern
- project convention
- stable summary of a subsystem

Properties:
- shared per project
- searchable
- human-readable
- medium to long retention
- writable only through explicit durable-write paths or promotion

## 2. `global_durable`

Purpose:
- store cross-project durable knowledge

Examples:
- general best practices
- cross-stack operational rules
- patterns proven reusable beyond one workspace

Properties:
- cross-project scope
- searchable
- human-readable
- longest retention
- stricter promotion threshold than `workspace_durable`

## 3. `session_scratch`

Purpose:
- hold temporary working context for one agent/session

Examples:
- task-local notes
- intermediate summaries
- working hypotheses not yet durable
- short-lived context handoff between executor steps

Properties:
- isolated by session policy
- not human-searchable by default
- not durable knowledge
- short retention
- can be read by gateway flows
- promotion-source only, not promotion-eligible by default

## 4. `payload_metadata_cache`

Purpose:
- support retry, observability, idempotency, and non-content diagnostics for payload preparation

Examples:
- request id
- input digest
- selected block ids
- source tiers accessed
- token counts
- latency metrics
- drop reasons

Properties:
- operational only
- non-searchable for human recall
- safe for restricted debug visibility
- short retention
- not promotion-eligible by default

## 5. `source_manifest`

Purpose:
- support deterministic rebuild for complex requests that involve files, parsing, extraction, or mutable sources

Examples:
- file refs
- content digests
- parser version
- extractor version
- page or chunk map

Properties:
- operational only
- non-searchable
- supports retry classification and rebuild lineage
- short retention
- not promotion-eligible

## 6. `retry_capsule`

Purpose:
- optionally retain a replayable payload snapshot for very short-lived retry when metadata and manifest are not enough

Examples:
- compiled prompt input
- extracted content snapshot for replay

Properties:
- ephemeral
- shortest retention
- not searchable
- never durable by default
- must not feed standard retrieval paths

Important note:
- this class exists for operations, not for memory reuse
- if the platform can operate with digests and manifests only, this class should stay minimal

## 7. `promotion_candidate`

Purpose:
- represent a runtime-originated artifact under evaluation for durable promotion

Examples:
- candidate rule
- candidate pattern
- candidate decision summary

Properties:
- temporary governance state
- not part of normal retrieval
- scored, rewritten, and approved before durable write
- may be rejected without ever entering durable memory

## Design Pushback

The risky temptation is to collapse `session_scratch`, `payload_metadata_cache`, and
`retry_capsule` into one generic runtime bucket.

That looks simpler, but it weakens governance:

- metadata should be debug-visible
- content should often remain opaque
- scratch state may be semantically useful within a session, while compiled payload content may not

So the split is justified, but it should not be expanded further unless a real
operational need appears.

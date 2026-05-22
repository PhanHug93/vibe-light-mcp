# Design Risks And Review Points

Status: draft

## Main Risks

### 1. Over-Splitting The Taxonomy

If too many artifact families are created, the platform becomes difficult to operate,
index, and explain.

Review question:
- do we have the minimum set, or are we naming implementation details as first-class concepts?

### 2. Under-Splitting The Runtime Plane

If metadata cache, source manifest, retry capsule, and session scratch are merged into
one runtime bucket, visibility and retention rules will become vague.

Review question:
- do we still have enough separation to keep debug safe and retrieval predictable?

### 3. Implicit Searchability

If searchability is inferred instead of explicit, runtime artifacts will eventually leak
into normal recall flows.

Review question:
- can every artifact answer "am I searchable?" without guessing?

### 4. Promotion Drift

If `promotion_candidate` behaves too much like durable memory, governance weakens.

Review question:
- is the candidate store clearly temporary and non-authoritative?

### 5. Operational Bloat

If `retry_capsule` is used too freely, the database will grow with little reuse value.

Review question:
- can most operational needs be satisfied by metadata and manifests instead of full payload retention?

### 6. Logical-Physical Confusion

If engineers assume logical families must map one-to-one to physical stores, the system
will become harder to operate without gaining proportional safety.

Review question:
- are we keeping policy taxonomy and storage topology intentionally separate?

## Architectural Recommendation

The safest operating posture is:

- durable memory remains small and curated
- runtime state remains short-lived
- debug remains opaque
- promotion remains the only learning bridge
- physical stores remain few until operational pressure justifies expansion

## Approval Criteria For This Spec

Approve this taxonomy only if:

1. every artifact family has a distinct behavioral reason to exist
2. visibility and searchability are explicit
3. runtime artifact families cannot silently become durable knowledge
4. the taxonomy is still small enough for engineers and agents to apply consistently
5. the logical model does not force unnecessary physical storage complexity

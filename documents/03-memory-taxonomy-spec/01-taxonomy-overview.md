# Taxonomy Overview

Status: draft

## Why Taxonomy Matters

The MCP platform now supports two different products:

- durable, human-readable memory
- ephemeral, executor-facing gateway state

Without an explicit taxonomy, both products will start writing similar-looking data
into the same logical memory surface. That would cause:

- retrieval ambiguity
- memory pollution
- inconsistent debug behavior
- accidental reuse of runtime artifacts as durable knowledge

## Taxonomy Principle

Artifact type must determine behavior.

At minimum, every artifact type must imply:

- persistence class
- searchability
- visibility
- promotion eligibility
- retention policy

## Minimal Canonical Set

The taxonomy should stay intentionally small:

1. `workspace_durable`
2. `global_durable`
3. `session_scratch`
4. `payload_metadata_cache`
5. `source_manifest`
6. `retry_capsule`
7. `promotion_candidate`

## Architectural Bias

This taxonomy is deliberately asymmetric:

- durable classes are optimized for reuse and readability
- runtime classes are optimized for execution continuity and observability

That asymmetry is not a flaw. It is the protection mechanism that keeps the system
from turning runtime traces into fake knowledge.

## Review Constraint

If a new artifact family cannot justify a unique combination of:

- reader set
- retention
- searchability
- governance

then it should not become a first-class type.

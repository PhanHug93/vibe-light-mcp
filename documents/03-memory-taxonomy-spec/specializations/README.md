# Artifact Type Specializations V1

Status: draft
Owner: architecture
Last updated: 2026-04-08

## Purpose

This folder defines `V1` specialization specs for durable artifact types.

These docs sit inside `03-memory-taxonomy-spec` because they refine artifact types,
not retrieval topology or promotion workflow as a whole.

## Scope

`V1` in this folder means:

- temporarily locked for the current architecture scope
- good enough to drive downstream specs and review
- still expected to evolve when retrieval, promotion, and governance become more concrete

## Available Specializations

- [01-principle-v1.md](./01-principle-v1.md)
- [02-rule-v1.md](./02-rule-v1.md)
- [03-pattern-v1.md](./03-pattern-v1.md)
- [04-problem-template-v1.md](./04-problem-template-v1.md)
- [05-playbook-v1.md](./05-playbook-v1.md)

## Design Rule

Each specialization must keep three layers separate:

1. content instance shape
2. type definition / promotion policy
3. machine-readable gate config

If these layers are mixed, the schema will drift and become harder to govern.

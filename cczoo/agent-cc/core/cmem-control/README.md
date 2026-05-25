# Confidential Memory Control Plane

`cmem-control` is the proposed home for a future Confidential Memory Control Plane for agent memory systems. This directory currently contains documentation only. It does not define a Python package, service entrypoint, runtime configuration, or implementation code.

The control plane is intended to sit beside memory frameworks rather than replace them. Its job is to make security decisions verifiable while each framework keeps its own memory model, storage, indexing, extraction, and runtime behavior.

## Purpose

The Confidential Memory Control Plane defines common contracts for:

- evidence verification
- policy decisions
- capability leases
- key-release decisions
- egress decisions
- metadata-only trusted decision ledger events
- adapter contracts for SDK, MCP, HTTP, host-plugin, context-engine, and runtime integrations

The central abstraction is the control plane. A verifier or policy gateway is only one deployment pattern.

## Scope

`cmem-control` owns trust and authorization semantics for confidential memory workflows. It does not own:

- memory extraction or summarization
- vector search or graph indexing
- privacy restore implementation
- session archive storage
- persona or skill generation
- agent runtime state transitions
- raw prompt, tool result, or memory plaintext persistence

## Relationship to Existing Core Components

`core/tlog` is the direct reusable foundation for trusted-log data models, deterministic digest helpers, and immutable-log adapter concepts.

`core/tc-api`, TruCon, and `tc-verify` are optional integration points. They provide useful existing patterns for attested-head evidence, evidence-backed verification, same-machine internal transport, and reserve/sign/commit trusted-log sequencing, but `cmem-control` should not inherit trusted-container build, publish, launch, or Docktap semantics.

## Documentation Map

- `docs/architecture.md`: component boundaries, dependency stance, trust model, file organization, and non-goals
- `docs/api.md`: evidence, policy, lease, key-release, egress, and audit/ledger API families
- `docs/event-vocabulary.md`: generic memory operations and metadata-only ledger event vocabulary
- `docs/deployment-profiles.md`: deployment variants and gateway suitability
- `docs/threat-model.md`: plaintext handling, fail-closed behavior, gateway anti-patterns, and assumptions
- `docs/overview_tasks.md`: standing future-work ledger

## Current Status

This is a documentation seed for future work. Applying this change should only add documentation and examples. Future implementation work should be proposed separately before adding packages, services, routes, or runtime integrations.
## Context

The repository already contains two relevant core building blocks:

- `core/tlog/`: a narrow trusted-log package with deterministic digest helpers, domain types, and immutable-log adapter interfaces.
- `core/tc-api/`: a trusted-container control plane that includes TruCon sequencing, attested-head evidence, `tc-verify`, Unix-domain-socket internal transport, and a reserve/sign/commit trusted-log pattern.

The OpenViking/OpenClaw integration currently has a bounded HTTP context-engine shape, while the broader agent-memory ecosystem includes SDK-style memory layers, MCP/REST memory servers, host-plugin memory frameworks, and full stateful agent runtimes. A generic confidential memory solution needs durable architecture docs before implementation because the boundary is cross-cutting and security-sensitive.

This change intentionally creates only documentation. It captures the proposed final file organization and adapter boundaries without adding runtime code.

## Goals / Non-Goals

**Goals:**

- Document `core/cmem-control/` as the future home for the Confidential Memory Control Plane.
- Document `cmem-control` as a generic control plane for attestation, policy decisions, capability leases, key-release decisions, egress decisions, and trusted decision-ledger events.
- Document that `cmem-control` directly reuses `tlog` concepts, while `tc-api`/TruCon/`tc-verify` remain optional integration points rather than a hard dependency on the whole trusted-container service.
- Document the intended `adapters/OpenViking/` structure, including OpenClaw local verify skill docs, gateway/sidecar docs, OpenViking evidence/posture contracts, route-to-operation mapping, and examples.
- Define docs-only tasks that can be applied and archived without modifying application code.

**Non-Goals:**

- Do not implement `core/cmem-control` as a Python package or service in this change.
- Do not add OpenViking endpoints, OpenClaw skills, gateway code, policy engine code, key broker code, or tests.
- Do not modify `core/tlog`, `core/tc-api`, OpenViking, OpenClaw plugin examples, or existing runtime behavior.
- Do not standardize memory schemas for mem0, agentmemory, TencentDB-Agent-Memory, Letta, or OpenViking.
- Do not store session plaintext, prompts, tool outputs, privacy-restored content, or raw memory values in the trusted decision ledger.

## Decisions

### Decision 1: Use `core/cmem-control/` as the component directory

The future Confidential Memory Control Plane documentation will live under `core/cmem-control/`.

Rationale:

- The name is short enough for routine use while preserving the confidential-memory meaning.
- It avoids `mcp`, which would collide conceptually with Model Context Protocol.
- It is clearer than a generic `memory-control-plane` because confidentiality, attestation, and policy are first-class parts of the component.

Alternatives considered:

- `core/confidential-memory-control-plane/`: explicit but long and cumbersome.
- `core/memory-control-plane/`: shorter but too generic.
- `core/cmem/`: short but ambiguous about whether it is a memory system or a control plane.

### Decision 2: Treat `cmem-control` as a control plane, not a memory framework

`cmem-control` will be documented as owning generic trust and policy semantics:

- evidence verification
- policy decisions
- capability leases
- key-release decisions
- egress decisions
- trusted decision-ledger event vocabulary
- generic adapter contracts

It will explicitly not own memory extraction, indexing, session storage, privacy restore implementation, vector search, persona generation, or agent runtime state.

Rationale: memory frameworks differ too much internally. The reusable layer is the trust decision and evidence model, not a universal memory schema.

### Decision 3: Depend directly on `tlog`, not directly on all of `tc-api`

The documentation will define this dependency stance:

```text
core/tlog
  -> direct reusable trusted-log model and digest dependency

core/tc-api / TruCon / tc-verify
  -> optional attested-ledger and verification integration
```

Rationale:

- `tlog` is intentionally narrow and suitable as a reusable trusted-log foundation.
- `tc-api` carries trusted-container build/publish/launch semantics that should not leak into a generic memory control plane.
- TruCon and `tc-verify` are valuable integration points, but `cmem-control` should be able to document its contract without inheriting the entire trusted-container service.

### Decision 4: Use a trusted decision ledger for metadata-only security events

The control-plane docs will describe a ledger that records canonical metadata-only decision predicates, such as:

- `policy.decision.allow`
- `policy.decision.deny`
- `policy.decision.fail_closed`
- `lease.issued`
- `lease.revoked`
- `key_release.allow`
- `key_release.deny`
- `egress.allow`
- `egress.deny`
- `materialize.allow`
- `materialize.deny`

Rationale: the ledger should prove security-relevant decisions and evidence state without becoming a sensitive memory data store.

### Decision 5: Put OpenViking-specific glue under `adapters/OpenViking/`

The OpenViking adapter docs will cover:

- architecture and overview tasks
- OpenClaw local verify skill contract
- optional verifier/policy gateway or sidecar deployment
- OpenViking evidence/posture endpoint contract
- route-to-operation mapping for `observe`, `recall`, `materialize`, `commit`, `delete`, `egress`, and `privacy_restore`
- policy and evidence examples

Rationale: OpenViking route semantics and OpenClaw trust-gate behavior are framework-specific. They should not be baked into the generic control plane.

### Decision 6: Define deployment variants explicitly

The docs will separate low-intrusion and complete target states:

- metadata-only policy mode
- gateway-protected remote memory mode
- attested memory service mode
- attestation-gated key-release mode
- confidential agent runtime mode

Rationale: a gateway is useful for service-style frameworks, but not universal enough for SDK-style or runtime-style systems. The architecture should describe gateway as a deployment option, not the central abstraction.

## Risks / Trade-offs

- Risk: The documentation may imply implementation commitments that are too broad for the first apply phase. Mitigation: keep tasks documentation-only and explicitly defer runtime implementation.
- Risk: `cmem-control` could become coupled to container-specific `tc-api` semantics. Mitigation: document direct dependency on `tlog` only and describe TruCon/`tc-verify` as optional integrations.
- Risk: A gateway design could accidentally inspect or persist session plaintext outside a confidential boundary. Mitigation: document metadata-only gateway invariants and mark plaintext-inspecting gateways as anti-patterns.
- Risk: OpenViking adapter docs may overfit OpenViking and fail to inform other memory frameworks. Mitigation: keep generic control-plane docs separate from OpenViking-specific route and skill docs.
- Risk: Documentation-only tasks may not be testable like runtime behavior. Mitigation: specs require concrete file existence, named sections, and explicit docs-only scope.

## Migration Plan

This change has no runtime migration. Applying it will only add documentation files.

Suggested apply order:

1. Create `core/cmem-control/` documentation and task ledger.
2. Create `adapters/OpenViking/` documentation, examples, and adapter task ledger.
3. Cross-link the docs to existing `core/tlog`, `core/tc-api`, and OpenViking design references where useful.
4. Verify no application code, package metadata, or runtime configuration was changed.

Rollback is deletion of the new documentation files and empty directories created by this change.

## Open Questions

- Should a later implementation extract shared attested-evidence primitives from `core/tc-api` into a smaller reusable package, or keep using `tc-api`/TruCon through service and CLI boundaries?
- Should the first implementation target OpenViking-only docs-to-code, or build a minimal generic `cmem-control` package first?
- Which chain-id taxonomy should become normative for tenants, deployments, and framework instances?
- Should `adapters/OpenViking/` eventually contain runnable skill/gateway code, or only reference implementations and configuration examples?
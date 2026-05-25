# OpenViking Confidential Memory Adapter Architecture

## Purpose

This documentation describes how OpenViking and OpenClaw can integrate with the proposed Confidential Memory Control Plane. It is documentation only. It does not add OpenViking endpoints, OpenClaw plugin code, gateway code, runtime configuration, or tests.

The center of the design is OpenViking as a confidential memory service for OpenClaw. OpenClaw should verify the target service or gateway before sending context, and failures should deny context transfer.

## Existing Integration Shape

OpenViking already has a documented OpenClaw plugin design where OpenClaw delegates three context-engine paths to OpenViking:

- `afterTurn`: lossless session capture
- `assemble`: context assembly and recall
- `compact`: archive and memory extraction commit

The existing plugin design is documented in `OpenViking/docs/design/openclaw-plugin-design.md`. That shape is useful because it gives the adapter a bounded set of operations to map into the control plane.

## Target Components

```text
OpenClaw
  -> local verify skill
  -> optional verifier/policy gateway or sidecar
  -> OpenViking confidential memory service
  -> optional cmem-control decision ledger
```

The generic control plane lives under `core/cmem-control/`. This adapter directory describes OpenViking-specific glue only.

## Deployment Variants

### Variant A: Local Verify Gate Only

```text
OpenClaw -> local verify skill -> OpenViking evidence/posture -> OpenViking API
```

OpenClaw calls a local verify skill before context transfer. The skill fetches evidence from OpenViking or a sidecar and denies context transfer when verification fails.

This is low intrusion if evidence is provided externally or through a small system/posture surface.

### Variant B: Verifier/Policy Gateway

```text
OpenClaw -> local verify skill -> gateway -> OpenViking
```

The gateway performs attestation checks, posture checks, policy prechecks, scoped header injection, and metadata-only decision recording. A non-confidential gateway must not inspect or persist session plaintext.

This is best for trust establishment and route-level policy. It cannot fully replace OpenViking-side hooks for privacy restore, archive materialization, memory extraction, or egress control.

### Variant C: OpenViking Confidential Core

```text
OpenClaw -> verified OpenViking -> OpenViking core policy hooks -> protected memory workflows
```

OpenViking itself enforces policy at recall, materialization, privacy restore, session capture, commit, and egress boundaries. This is the complete target state, but it is more invasive than a gateway-only deployment.

### Variant D: Attestation-Gated Key Release

```text
OpenViking evidence -> cmem-control -> key broker -> scoped key lease
```

Keys or key handles are released only after evidence and policy pass. This belongs in a future implementation proposal.

## Adapter Responsibilities

The OpenViking adapter documentation owns:

- local verify skill contract
- evidence and posture claim expectations
- route-to-operation mapping
- gateway suitability and anti-patterns
- examples for policy, evidence, and decision events
- future task tracking

The adapter does not own:

- OpenViking session storage
- OpenViking memory extraction internals
- OpenViking privacy restore implementation
- OpenClaw runtime implementation
- generic `cmem-control` policy engine implementation

## Security Invariants

- OpenClaw must fail closed before sending context when verification is unavailable or fails.
- Gateway-hosted evidence is acceptable, but gateway plaintext inspection outside a confidential boundary is not.
- `materialize` paths are more sensitive than ordinary `recall` paths.
- External model and embedding calls are egress decisions.
- Trusted decision events record metadata, hashes, scopes, policy identifiers, evidence references, and outcomes, not memory plaintext.

## Complete Target State

The complete confidential memory service target eventually needs OpenViking-side policy hooks for:

- session message capture
- session context recall
- content and archive materialization
- privacy restore
- memory extraction and commit
- external LLM or embedding egress

This documentation-only change does not implement those hooks.
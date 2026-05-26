# Confidential Memory Control Plane Task Overview

> Purpose: standing future-work ledger for the proposed `core/cmem-control` component.
> Status: documentation seed plus a minimal archived reference slice for OpenViking `send_context`; broader runtime implementation remains open.

## Task Format

Each item uses:

- ID: `GAP-CMEM-<number>` for missing future capabilities, `DOC-CMEM-<number>` for documentation follow-up
- Priority: HIGH / MEDIUM / LOW
- Scope: affected documentation or future component area
- Acceptance Criteria: concrete conditions for completion

## Current Documentation Tasks

### DOC-CMEM-01: Maintain Control-Plane Architecture Documentation

- Priority: HIGH
- Scope: `core/cmem-control/docs/architecture.md`
- Status: SEEDED
- Acceptance Criteria:
  1. The docs describe the component as a control plane, not a memory framework.
  2. The docs describe `core/tlog` as the direct reusable foundation.
  3. The docs describe `core/tc-api`/TruCon/`tc-verify` as optional integrations.

### DOC-CMEM-02: Maintain API Contract Documentation

- Priority: HIGH
- Scope: `core/cmem-control/docs/api.md`
- Status: SEEDED
- Acceptance Criteria:
  1. Evidence, policy, lease, key-release, egress, and audit/ledger API families remain documented.
  2. Request examples remain metadata-oriented and plaintext-free.

### DOC-CMEM-03: Maintain Event Vocabulary Documentation

- Priority: HIGH
- Scope: `core/cmem-control/docs/event-vocabulary.md`
- Status: SEEDED
- Acceptance Criteria:
  1. Generic operations include observe, recall, materialize, commit, delete, egress, privacy_restore, key_release, and lease.
  2. Materialization remains documented as higher sensitivity than recall.

## Future Implementation Planning

### GAP-CMEM-01: Define Runtime Package Boundaries

- Priority: HIGH
- Scope: future `cmem_control` package proposal
- Status: NOT STARTED
- Acceptance Criteria:
  1. A future proposal defines package modules before code is added.
  2. The package boundary avoids direct dependency on container-specific `tc-api` workflows.

### GAP-CMEM-02: Define Evidence Verification Adapter

- Priority: HIGH
- Scope: evidence verification
- Status: IN PROGRESS
- Current State: The archived change `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/` added a reference verification slice in `core/tc-api` for OpenViking `send_context`, including attested-head-compatible evidence validation, freshness checks, binding checks, policy compatibility checks, and fail-closed denial behavior.
- Implemented Subtasks:
  1. ~~`GAP-CMEM-02A` — Minimal OpenViking evidence verification slice~~ ✅ COMPLETED
     - Completed: 2026-05-25 | Archive: `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/`
     - Outcome: A reference verifier accepts OpenViking evidence, validates freshness, ledger binding, policy fields, and failure reasons, and exposes a five-minute trust-cache model for `send_context` decisions.
- Remaining Scope:
  1. Generalize the verification surface beyond OpenViking-specific response models.
  2. Define the future package boundary for a reusable `cmem_control` verification adapter independent of the `tc-api` runtime.
- Acceptance Criteria:
  1. A future implementation can verify attested-head evidence or call an external verifier.
  2. Verification results include freshness, binding, policy, and failure reasons.

### GAP-CMEM-03: Define Policy Decision Engine

- Priority: HIGH
- Scope: policy decisions
- Status: IN PROGRESS
- Current State: The archived OpenViking context-gate slice now exercises a minimal `allow` or `deny` decision model for `send_context`, but it does not yet define a reusable operation-agnostic policy engine.
- Implemented Subtasks:
  1. ~~`GAP-CMEM-03A` — Minimal `send_context` decision slice~~ ✅ COMPLETED
     - Completed: 2026-05-25 | Archive: `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/`
     - Outcome: The reference implementation supports `allow` and fail-closed `deny` decisions for `send_context`, bound to evidence, policy identifier, policy version, and decision metadata.
- Remaining Scope:
  1. Generalize decisions across `observe`, `recall`, `materialize`, `commit`, `privacy_restore`, and `egress`.
  2. Decide whether `degraded` remains a real runtime verdict or is restricted to non-sensitive paths.
- Acceptance Criteria:
  1. Policy decisions support allow, deny, fail_closed, and degraded results.
  2. Decisions are bound to subject, resource, operation, purpose, and evidence.

### GAP-CMEM-04: Define Trusted Decision Ledger Integration

- Priority: HIGH
- Scope: ledger recorder and `tlog` integration
- Status: IN PROGRESS
- Current State: The archived OpenViking context-gate slice now emits metadata-only `context_send.allow` and `context_send.deny` decision records, but it stops short of a generalized `tlog`-backed ledger recorder.
- Implemented Subtasks:
  1. ~~`GAP-CMEM-04A` — Minimal context-send decision record~~ ✅ COMPLETED
     - Completed: 2026-05-25 | Archive: `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/`
     - Outcome: The reference slice records metadata-only allow or deny decisions without prompt, context, archive, or memory plaintext.
- Remaining Scope:
  1. Canonicalize the broader decision-event family against `tlog` types and digest helpers.
  2. Decide whether ledger recording is synchronous, policy-conditional, or best-effort for each operation class.
- Acceptance Criteria:
  1. Decision events are canonicalized and digestible.
  2. Ledger recording excludes memory plaintext.
  3. TruCon integration remains optional.

### GAP-CMEM-05: Define Capability Lease Semantics

- Priority: MEDIUM
- Scope: leases
- Status: NOT STARTED
- Acceptance Criteria:
  1. Leases are scoped by subject, resource, operation set, purpose, TTL, policy version, and evidence head.
  2. Lease revocation is auditable.

### GAP-CMEM-06: Define Key-Release Decision Semantics

- Priority: MEDIUM
- Scope: key release
- Status: NOT STARTED
- Acceptance Criteria:
  1. Key release requires evidence verification and policy authorization.
  2. Key release events are logged as high-value trusted decisions.

### GAP-CMEM-07: Define Egress Decision Semantics

- Priority: MEDIUM
- Scope: egress
- Status: NOT STARTED
- Acceptance Criteria:
  1. External LLM and embedding calls are classified as egress.
  2. Egress decisions include destination, payload class, purpose, and policy version.
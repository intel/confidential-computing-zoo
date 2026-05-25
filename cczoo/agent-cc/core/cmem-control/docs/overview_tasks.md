# Confidential Memory Control Plane Task Overview

> Purpose: standing future-work ledger for the proposed `core/cmem-control` component.
> Status: documentation seed only; no runtime implementation is completed by this change.

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
- Status: NOT STARTED
- Acceptance Criteria:
  1. A future implementation can verify attested-head evidence or call an external verifier.
  2. Verification results include freshness, binding, policy, and failure reasons.

### GAP-CMEM-03: Define Policy Decision Engine

- Priority: HIGH
- Scope: policy decisions
- Status: NOT STARTED
- Acceptance Criteria:
  1. Policy decisions support allow, deny, fail_closed, and degraded results.
  2. Decisions are bound to subject, resource, operation, purpose, and evidence.

### GAP-CMEM-04: Define Trusted Decision Ledger Integration

- Priority: HIGH
- Scope: ledger recorder and `tlog` integration
- Status: NOT STARTED
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
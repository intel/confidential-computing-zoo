# OpenViking Confidential Memory Adapter Task Overview

> Purpose: standing future-work ledger for OpenViking/OpenClaw confidential memory adapter work.
> Status: documentation seed only; no runtime implementation is completed by this change.

## Current Documentation Tasks

### DOC-OV-01: Maintain Adapter Architecture Documentation

- Priority: HIGH
- Scope: `adapters/OpenViking/architecture.md`
- Status: SEEDED
- Acceptance Criteria:
  1. Deployment variants remain documented.
  2. Low-intrusion gateway mode and complete OpenViking confidential core mode remain distinct.
  3. Fail-closed context transfer remains explicit.

### DOC-OV-02: Maintain Adapter API Contract Documentation

- Priority: HIGH
- Scope: `adapters/OpenViking/api.md`
- Status: SEEDED
- Acceptance Criteria:
  1. Local verify skill flow remains documented.
  2. Evidence and posture claims remain listed.
  3. Route classes remain mapped to generic control-plane operations.

### DOC-OV-03: Maintain Examples

- Priority: MEDIUM
- Scope: `adapters/OpenViking/examples/`
- Status: SEEDED
- Acceptance Criteria:
  1. Example policy remains documentation-only.
  2. Evidence and decision-event examples contain no secrets or memory plaintext.

## Future Implementation Planning

### GAP-OV-01: Implement Local Verify Skill

- Priority: HIGH
- Scope: future OpenClaw skill implementation
- Status: NOT STARTED
- Acceptance Criteria:
  1. OpenClaw can invoke the skill before context transfer.
  2. The skill verifies evidence-backed claims and fails closed on errors.

### GAP-OV-02: Define Evidence/Posture Provider

- Priority: HIGH
- Scope: OpenViking, gateway, or sidecar evidence surface
- Status: NOT STARTED
- Acceptance Criteria:
  1. Evidence exposes deployment identity, instance identity, policy version, ledger head, freshness, and egress posture.
  2. Evidence can be verified with `tc-verify`-compatible semantics when TruCon integration is used.

### GAP-OV-03: Define Gateway Route Policy

- Priority: MEDIUM
- Scope: optional verifier/policy gateway
- Status: NOT STARTED
- Acceptance Criteria:
  1. Gateway route policy classifies observe, recall, materialize, commit, privacy_restore, and egress.
  2. Gateway policy remains metadata-only outside a confidential boundary.

### GAP-OV-04: Add OpenViking Core Policy Hooks

- Priority: MEDIUM
- Scope: future OpenViking implementation proposal
- Status: NOT STARTED
- Acceptance Criteria:
  1. Policy hooks cover session capture, recall, content read, archive materialization, privacy restore, commit, and egress.
  2. Hooks preserve existing OpenViking memory semantics.

### GAP-OV-05: Define Attestation-Gated Key Release

- Priority: LOW
- Scope: future key broker integration
- Status: NOT STARTED
- Acceptance Criteria:
  1. Key release requires verified OpenViking evidence and policy authorization.
  2. Key release decisions are recorded as trusted decision events.
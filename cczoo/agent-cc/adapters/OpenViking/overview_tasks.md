# OpenViking Confidential Memory Adapter Task Overview

> Purpose: standing future-work ledger for OpenViking/OpenClaw confidential memory adapter work.
> Status: documentation seed plus a minimal archived trusted-context-gate reference slice; deeper OpenViking and OpenClaw integration work remains open.

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
- Status: IN PROGRESS
- Current State: The archived change `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/` added a reference local verify-skill implementation in `core/tc-api`, but it does not yet wire a real OpenClaw runtime invocation path.
- Implemented Subtasks:
  1. ~~`GAP-OV-01A` — Reference local verify-skill implementation~~ ✅ COMPLETED
     - Completed: 2026-05-25 | Archive: `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/`
     - Outcome: `tc-openviking-verify-context` verifies dedicated evidence before `send_context`, fails closed on verification problems, and reuses successful verification for up to five minutes.
- Remaining Scope:
  1. Decide the real OpenClaw integration surface for invoking the local verify skill before context transfer.
  2. Define the packaging and operator contract for deploying that skill with OpenClaw.
- Acceptance Criteria:
  1. OpenClaw can invoke the skill before context transfer.
  2. The skill verifies evidence-backed claims and fails closed on errors.

### GAP-OV-02: Define Evidence/Posture Provider

- Priority: HIGH
- Scope: OpenViking, gateway, or sidecar evidence surface
- Status: IN PROGRESS
- Current State: The archived trusted-context-gate change added dedicated `/confidential/evidence/{chain_id}` and `/confidential/posture/{chain_id}` reference surfaces in `core/tc-api`, but it does not yet establish an OpenViking-native or sidecar-native provider deployment.
- Implemented Subtasks:
  1. ~~`GAP-OV-02A` — Reference evidence and posture surfaces~~ ✅ COMPLETED
     - Completed: 2026-05-25 | Archive: `openspec/changes/archive/2026-05-25-openviking-minimal-trusted-context-gate/`
     - Outcome: The reference surface exposes dedicated evidence and posture contracts, required context-send claims, freshness bounds, and attested-head-compatible verification material.
- Remaining Scope:
  1. Decide whether the production provider is OpenViking-native, a sidecar, or a gateway-bound surface.
  2. Clarify how deployment identity, instance identity, and measurement are bound to the actual OpenViking runtime rather than only to the reference service.
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
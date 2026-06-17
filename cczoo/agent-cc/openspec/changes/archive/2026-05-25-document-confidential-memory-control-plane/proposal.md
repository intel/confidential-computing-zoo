## Why

The repository has converged on a broader architecture for confidential agent memory: a reusable Confidential Memory Control Plane backed by verifiable trusted-log evidence, plus thin adapters for memory frameworks such as OpenViking/OpenClaw. That architecture is currently captured only in discussion, so implementation would be premature without durable docs that define scope, file organization, trust boundaries, and documentation-only follow-up tasks.

## What Changes

- Add documentation under `core/cmem-control/` describing the proposed Confidential Memory Control Plane component, including its purpose, dependency stance, API surface, deployment profiles, trusted decision ledger, event vocabulary, and task ledger.
- Add documentation under `adapters/OpenViking/` describing how OpenViking/OpenClaw should adapt to the control plane through a local verify skill, optional verifier/policy gateway, evidence/posture contracts, route-to-operation mapping, and deployment variants.
- Document that `core/cmem-control/` directly depends on `core/tlog` concepts and treats `core/tc-api`/TruCon/`tc-verify` as an optional verification and attested-ledger integration rather than a hard dependency on the whole trusted-container service.
- Document the intended low-intrusion posture: the control plane records metadata-only security decisions and evidence digests, while memory frameworks retain their existing memory models and avoid sending session plaintext to non-confidential gateways.
- Add a standing task overview for documentation and future implementation planning only.
- This change is documentation-only. It does not add Python packages, service code, OpenViking code changes, OpenClaw plugin changes, runtime configuration, or tests.

## Capabilities

### New Capabilities

- `confidential-memory-control-plane-docs`: Documents the generic Confidential Memory Control Plane architecture, APIs, evidence model, trusted decision ledger, dependency boundaries, deployment profiles, and task ledger under `core/cmem-control/`.
- `openviking-cmem-adapter-docs`: Documents the OpenViking/OpenClaw adapter architecture, local verify skill, gateway/sidecar options, evidence/posture contracts, route-to-operation mapping, policy examples, and task ledger under `adapters/OpenViking/`.

### Modified Capabilities

- None.

## Impact

- Affected paths are documentation-only:
  - `core/cmem-control/**`
  - `adapters/OpenViking/**`
- The proposal references existing `core/tlog` and `core/tc-api` concepts but does not modify those components.
- The proposal references existing OpenViking/OpenClaw integration paths but does not modify OpenViking, OpenClaw plugin code, or runtime behavior.
- No breaking changes.
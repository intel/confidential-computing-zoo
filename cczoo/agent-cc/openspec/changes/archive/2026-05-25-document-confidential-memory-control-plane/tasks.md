## 1. Core Confidential Memory Control Plane Docs

- [x] 1.1 Create `core/cmem-control/README.md` describing the component purpose, docs-only status, scope, and relationship to confidential agent memory.
- [x] 1.2 Create `core/cmem-control/docs/architecture.md` covering component boundaries, dependency stance, trust model, control-plane responsibilities, non-goals, and file organization.
- [x] 1.3 Create `core/cmem-control/docs/api.md` documenting evidence, policy decision, capability lease, key-release, egress decision, and audit/ledger API families at the contract level.
- [x] 1.4 Create `core/cmem-control/docs/event-vocabulary.md` defining metadata-only decision events and generic memory operations including observe, recall, materialize, commit, delete, egress, privacy_restore, key_release, and lease.
- [x] 1.5 Create `core/cmem-control/docs/deployment-profiles.md` distinguishing metadata-only policy mode, gateway-protected remote memory mode, attested memory service mode, attestation-gated key-release mode, and confidential agent runtime mode.
- [x] 1.6 Create `core/cmem-control/docs/threat-model.md` documenting plaintext handling rules, fail-closed behavior, gateway anti-patterns, ledger sensitivity, and trust-boundary assumptions.
- [x] 1.7 Create `core/cmem-control/docs/overview_tasks.md` as a standing future-work ledger for control-plane documentation and later implementation planning.

## 2. OpenViking Adapter Docs

- [x] 2.1 Create `adapters/OpenViking/architecture.md` describing the OpenViking/OpenClaw adapter architecture, deployment variants, low-intrusion gateway mode, and complete confidential memory service target.
- [x] 2.2 Create `adapters/OpenViking/api.md` documenting OpenClaw local verify skill behavior, evidence/posture claims, gateway-hosted evidence option, and fail-closed semantics.
- [x] 2.3 Create `adapters/OpenViking/overview_tasks.md` as a standing future-work ledger for OpenViking adapter documentation and later implementation planning.
- [x] 2.4 Create `adapters/OpenViking/openclaw-skill/README.md` documenting the local verify skill contract, expected inputs/outputs, evidence-backed verification, and denial behavior.
- [x] 2.5 Create `adapters/OpenViking/gateway/README.md` documenting verifier/policy gateway suitability, metadata-only forwarding constraints, route policy responsibilities, and anti-patterns.
- [x] 2.6 Create `adapters/OpenViking/openviking-extension/evidence_endpoint_spec.md` documenting minimum evidence/posture claims expected from OpenViking or a sidecar/gateway.
- [x] 2.7 Create `adapters/OpenViking/openviking-extension/event_mapping.md` mapping OpenViking context-engine routes and behaviors to generic control-plane operations.

## 3. Examples and Cross-References

- [x] 3.1 Create `adapters/OpenViking/examples/cmem-control.policy.example.yaml` showing documentation-only example policy shape for OpenViking/OpenClaw integration.
- [x] 3.2 Create `adapters/OpenViking/examples/evidence.sample.json` showing a non-secret attested-head evidence example aligned with the documented claims.
- [x] 3.3 Create `adapters/OpenViking/examples/decision-event.sample.json` showing a metadata-only trusted decision event without session plaintext.
- [x] 3.4 Cross-reference relevant existing docs and code concepts from `core/tlog`, `core/tc-api`, and OpenViking design docs without modifying those source components.

## 4. Documentation-Only Verification

- [x] 4.1 Verify that this change adds only documentation and example files under `core/cmem-control/**` and `adapters/OpenViking/**`.
- [x] 4.2 Verify that no Python package, service entrypoint, OpenViking runtime code, OpenClaw plugin runtime code, package metadata, or runtime configuration was added.
- [x] 4.3 Verify the new docs explicitly state that the trusted decision ledger records metadata, hashes, scopes, policy identifiers, evidence references, and outcomes rather than memory plaintext.
- [x] 4.4 Verify the new docs explicitly describe `core/tlog` as a direct reusable foundation and `core/tc-api`/TruCon/`tc-verify` as optional integrations.
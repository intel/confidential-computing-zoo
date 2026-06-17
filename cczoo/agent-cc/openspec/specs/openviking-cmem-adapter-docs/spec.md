# openviking-cmem-adapter-docs Specification

## Purpose
TBD - created by archiving change document-confidential-memory-control-plane. Update Purpose after archive.
## Requirements
### Requirement: OpenViking adapter documentation set
The change SHALL add a documentation set under `adapters/OpenViking/` that describes how OpenViking/OpenClaw can integrate with the Confidential Memory Control Plane without adding runtime code.

#### Scenario: Adapter docs exist
- **WHEN** the documentation-only change is applied
- **THEN** `adapters/OpenViking/architecture.md`, `adapters/OpenViking/api.md`, and `adapters/OpenViking/overview_tasks.md` exist and describe the adapter purpose, scope, and docs-only status

#### Scenario: No adapter runtime is introduced
- **WHEN** the documentation-only change is applied
- **THEN** the change does not add runnable OpenViking code, OpenClaw plugin code, gateway service code, package metadata, or runtime configuration

### Requirement: Local verify skill contract documentation
The OpenViking adapter documentation SHALL describe the local OpenClaw verify-skill trust gate and its fail-closed behavior.

#### Scenario: Verify skill flow is documented
- **WHEN** a reader opens the OpenViking architecture or API documentation
- **THEN** it describes a flow where OpenClaw calls a local verify skill before sending context, the skill verifies OpenViking or gateway evidence, and context transfer is denied when verification fails or is unavailable

#### Scenario: Evidence-backed verification is referenced
- **WHEN** a reader reviews the verify-skill contract
- **THEN** it explains that the skill is expected to use evidence-backed verification semantics compatible with the repository's `tc-verify` and attested-head evidence model

### Requirement: OpenViking evidence and posture contract documentation
The OpenViking adapter documentation SHALL define the minimum evidence and posture claims needed for OpenClaw or a verifier gateway to trust an OpenViking confidential memory service.

#### Scenario: Evidence claims are listed
- **WHEN** a reader opens the adapter API documentation
- **THEN** it lists claims such as deployment identity, service instance identity, TEE type, measurement or evidence reference, policy version, ledger chain identifier, ledger head identifier, evidence freshness, egress mode, and privacy-restore posture

#### Scenario: Gateway-hosted evidence is allowed
- **WHEN** a reader reviews deployment variants
- **THEN** it explains that evidence/posture claims may be exposed by OpenViking itself or by an external verifier/policy gateway or sidecar, depending on the intrusion level

### Requirement: Route-to-operation mapping documentation
The OpenViking adapter documentation SHALL map relevant OpenViking/OpenClaw context-engine routes and behaviors to generic Confidential Memory Control Plane operations.

#### Scenario: Existing routes are categorized
- **WHEN** a reader opens the route mapping documentation
- **THEN** it maps status, search, content read, session message, session context, session commit, archive/content expansion, privacy restore, and external egress behaviors to generic operations such as `observe`, `recall`, `materialize`, `commit`, `egress`, and `privacy_restore`

#### Scenario: Materialization is distinct from recall
- **WHEN** a reader reviews content-read or archive-expansion routes
- **THEN** those behaviors are identified as materialization-sensitive paths rather than ordinary recall-only paths

### Requirement: Gateway and sidecar suitability documentation
The OpenViking adapter documentation SHALL distinguish when an optional verifier/policy gateway is useful and when OpenViking-side hooks are still required.

#### Scenario: Low-intrusion gateway mode is documented
- **WHEN** a reader reviews deployment variants
- **THEN** the documentation describes a low-intrusion mode where a gateway or sidecar handles attestation, posture, policy prechecks, and metadata-only audit without inspecting session plaintext outside a confidential boundary

#### Scenario: Core memory hooks remain in scope for complete target state
- **WHEN** a reader reviews the complete confidential memory service target
- **THEN** the documentation states that privacy restore, archive materialization, session capture, memory extraction, and egress control may require OpenViking-side integration beyond a gateway

### Requirement: OpenViking adapter task ledger
The change SHALL add a standing task overview for OpenViking adapter documentation and future implementation planning.

#### Scenario: Adapter future tasks are documented
- **WHEN** a reader opens `adapters/OpenViking/overview_tasks.md`
- **THEN** it lists future work items for local verify skill docs, evidence/posture contracts, route mapping, gateway policy examples, deployment variants, and future implementation readiness without marking runtime implementation as completed by this change


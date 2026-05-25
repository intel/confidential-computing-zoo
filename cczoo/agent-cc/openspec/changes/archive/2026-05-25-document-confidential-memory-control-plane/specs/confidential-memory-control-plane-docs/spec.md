## ADDED Requirements

### Requirement: Core control-plane documentation set
The change SHALL add a documentation set under `core/cmem-control/` that describes the Confidential Memory Control Plane as a future core component without adding runtime code.

#### Scenario: Documentation root exists
- **WHEN** the documentation-only change is applied
- **THEN** `core/cmem-control/README.md` and `core/cmem-control/docs/architecture.md` exist and describe the component purpose, scope, and docs-only status

#### Scenario: No runtime package is introduced
- **WHEN** the documentation-only change is applied
- **THEN** the change does not add a `cmem_control` Python package, service entrypoint, package metadata, or runtime configuration

### Requirement: Dependency boundary documentation
The core documentation SHALL describe `core/tlog` as the direct reusable trusted-log foundation and `core/tc-api`/TruCon/`tc-verify` as optional integration points rather than mandatory dependencies on the full trusted-container service.

#### Scenario: Dependency stance is explicit
- **WHEN** a reader opens the core architecture documentation
- **THEN** the documentation states that `cmem-control` may reuse `tlog` concepts directly and may integrate with `tc-api`/TruCon/`tc-verify` through service, CLI, or adapter boundaries

#### Scenario: Container-specific semantics are excluded
- **WHEN** a reader reviews the non-goals or boundaries
- **THEN** the documentation states that build, publish, launch, Docktap, and container lifecycle semantics are not owned by the confidential memory control plane

### Requirement: Control-plane API and operation vocabulary documentation
The core documentation SHALL define the generic control-plane operation vocabulary and API families needed for confidential memory integrations.

#### Scenario: API families are documented
- **WHEN** a reader opens the API documentation
- **THEN** it describes evidence verification, policy decision, capability lease, key-release decision, egress decision, and audit/ledger decision APIs

#### Scenario: Memory operations are mapped generically
- **WHEN** a reader opens the event vocabulary documentation
- **THEN** it defines generic operations including `observe`, `recall`, `materialize`, `commit`, `delete`, `egress`, `privacy_restore`, `key_release`, and `lease`

### Requirement: Trusted decision ledger documentation
The core documentation SHALL describe a metadata-only trusted decision ledger that records verifiable security decisions without storing memory plaintext.

#### Scenario: Decision events are metadata-only
- **WHEN** a reader opens the ledger or event vocabulary documentation
- **THEN** it states that decision events record canonical metadata, scopes, hashes, policy identifiers, evidence digests, and outcomes rather than prompts, tool outputs, session plaintext, privacy-restored values, or raw memory contents

#### Scenario: Materialization is treated as sensitive
- **WHEN** a reader reviews the event vocabulary
- **THEN** `materialize.allow` and `materialize.deny` are identified as first-class ledger events distinct from lower-risk recall events

### Requirement: Deployment profile documentation
The core documentation SHALL distinguish gateway use from the more general control-plane abstraction.

#### Scenario: Gateway is not the universal abstraction
- **WHEN** a reader opens the deployment profile documentation
- **THEN** it states that a verifier/policy gateway is one deployment pattern, while SDK, MCP, host-plugin, context-engine, and runtime integrations may use different adapter shapes

#### Scenario: Profiles cover target states
- **WHEN** a reader reviews deployment profiles
- **THEN** the documentation covers metadata-only policy mode, gateway-protected remote memory mode, attested memory service mode, attestation-gated key-release mode, and confidential agent runtime mode

### Requirement: Core task ledger
The change SHALL add a standing task overview under `core/cmem-control/docs/` for future documentation and implementation planning.

#### Scenario: Future tasks are documented without implementation
- **WHEN** a reader opens the core task overview
- **THEN** it lists future work items for event vocabulary, evidence contracts, policy decisions, leases, key release, egress, ledger integration, and verification without marking any runtime implementation as completed by this change
## Purpose

Define the Rekor `intoto` upload and attestation-storage requirements for replayable records, including verifier materialization precedence and real-Rekor coverage.

## Requirements

### Requirement: Rekor upload path supports `intoto` v0.0.2 for replayable records
The system SHALL support uploading replayable tc_api records to Rekor as `intoto` v0.0.2 entries while preserving the existing internal Sigstore bundle contract between tc_api, TruCon, and the embedded submit daemon.

#### Scenario: Adapter converts bundle into intoto proposed entry
- **WHEN** `SigstoreLogAdapter.submit_bundle()` handles a replayable bundle under the intoto upload path
- **THEN** it SHALL construct a Rekor `intoto` v0.0.2 proposed entry from the signed bundle rather than posting the bundle as a DSSE-type entry

#### Scenario: Internal bundle storage remains unchanged
- **WHEN** tc_api commits a replayable record that will later be uploaded as an intoto Rekor entry
- **THEN** tc_api and TruCon SHALL continue to persist and exchange the original Sigstore bundle JSON as the internal commit artifact

### Requirement: Replayable intoto entries expose attestation-backed payload material
For replayable records uploaded through the intoto path, immutable replay SHALL be able to recover verifier-critical payload facts from the Rekor entry's attestation storage output.

#### Scenario: Attestation payload material is normalized for replay
- **WHEN** a public Rekor `intoto` entry returns a top-level `attestation` payload and the body does not contain directly replayable predicate fields
- **THEN** the verifier SHALL normalize that attestation into replayable payload facts that can be used for predecessor verification and structured output

#### Scenario: Attestation payload hash must match committed body hash
- **WHEN** the verifier consumes a Rekor `intoto` attestation as replay material
- **THEN** it SHALL validate that the attestation content matches the payload hash recorded in the committed body before treating the attestation as authoritative replay material

### Requirement: Attestation storage is preferred over OCI mirror for replay materialization
When replayable payload fields are missing from the public body, the verifier SHALL prefer Rekor attestation storage over OCI mirror fallback.

#### Scenario: Attestation storage available and mirror also configured
- **WHEN** immutable replay can recover the required predecessor payload from Rekor attestation storage and OCI mirror is also configured
- **THEN** the verifier SHALL use the attestation-storage materialization path first rather than requiring OCI mirror resolution

#### Scenario: Mirror remains fallback when attestation is unavailable
- **WHEN** the public Rekor body is hash-only and attestation storage is unavailable or invalid but a configured OCI mirror can resolve the required payload material
- **THEN** the verifier SHALL fall back to mirror-backed materialization rather than failing immediately

### Requirement: Real Rekor integration proves intoto upload and verify without OCI mirror
The system SHALL include real-Rekor integration coverage that proves replayable records uploaded as `intoto` can be verified through public Rekor plus attestation storage without OCI mirror.

#### Scenario: Real Rekor round-trip returns attestation-backed replay material
- **WHEN** the real-Rekor integration suite uploads a replayable record through the intoto path
- **THEN** the suite SHALL confirm that retrieval exposes enough attestation-backed material to normalize the signed payload for replay

#### Scenario: Multi-entry predecessor proof succeeds without mirror
- **WHEN** the real-Rekor integration suite verifies a replayable chain containing Event Log 0 and at least one later record after clearing process-local cache and without OCI mirror
- **THEN** the suite SHALL prove signed predecessor continuity through public Rekor plus attestation storage alone
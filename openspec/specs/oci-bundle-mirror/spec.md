## Purpose

Define the OCI-backed mirror requirements for replayable `bundle.json` publication and retrieval.

## Requirements

### Requirement: Replayable bundles are mirrored after Rekor confirmation
For newly written replayable chain nodes, the system SHALL publish the original `bundle.json` to an OCI-backed mirror only after the corresponding Rekor log entry is confirmed.

#### Scenario: Confirmed Rekor entry triggers mirror publication
- **WHEN** a replayable bundle is committed and Rekor returns a confirmed immutable-log entry for that node
- **THEN** the system SHALL enqueue or perform mirror publication for that node's original `bundle.json` after confirmation rather than before confirmation

#### Scenario: Mirror publication failure does not revoke Rekor confirmation
- **WHEN** Rekor confirmation succeeds but OCI mirror publication fails or is delayed
- **THEN** the committed node SHALL remain a confirmed immutable-log record and the system SHALL preserve mirror publication as a retryable follow-up concern

### Requirement: Mirror lookup is content-addressed by payload hash
The system SHALL resolve mirrored replayable bundles by `payload_hash` as the primary lookup key and SHALL NOT require human-readable chain labels as the primary authority for bundle retrieval.

#### Scenario: Resolve mirrored bundle from predecessor lookup hash
- **WHEN** replay verification needs to recover predecessor material for a record whose signed predecessor contract includes `prev_lookup_hash`
- **THEN** the mirror resolver SHALL use that payload hash as the primary lookup anchor for mirrored bundle retrieval

#### Scenario: Human-readable fields remain secondary indexes
- **WHEN** the system publishes or documents mirrored bundle lookup behavior
- **THEN** any use of `chain_id`, `sequence_num`, `event_digest`, or `rekor_log_id` SHALL be treated as secondary indexing or annotation rather than as the primary retrieval key

### Requirement: OCI mirror feasibility is proven before rollout
The change SHALL include a focused feasibility harness that proves OCI mirror publication and retrieval semantics for mirrored replayable bundles.

#### Scenario: Feasibility harness proves round-trip bundle retrieval
- **WHEN** the OCI mirror feasibility harness publishes a replayable `bundle.json`
- **THEN** it SHALL retrieve the mirrored object intact and confirm that the recovered bundle matches the original signed bundle material

#### Scenario: Feasibility harness proves missing mirror behavior
- **WHEN** the OCI mirror feasibility harness runs verification with mirror-required or mirror-optional policy while mirrored content is absent or delayed
- **THEN** it SHALL demonstrate deterministic verifier behavior for those missing-content cases rather than leaving them undefined
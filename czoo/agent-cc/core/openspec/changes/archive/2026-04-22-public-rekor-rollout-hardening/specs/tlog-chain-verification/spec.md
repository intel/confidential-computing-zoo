## ADDED Requirements

### Requirement: Public Rekor replay defines rollout-boundary semantics
`TrustedLogAPI.verify_record()` SHALL classify replay-regime boundaries separately from ordinary predecessor-proof mismatch when immutable-backend replay spans legacy linkage and reservation-backed signed predecessor proof. The structured result SHALL preserve a machine-readable boundary classification that distinguishes supported reservation-backed replay from degraded migration boundaries and from invalid regressions back to legacy linkage after the reservation-backed regime has begun.

#### Scenario: Reservation-backed replay remains supported
- **WHEN** immutable-backend replay begins at Event Log 0 under the reservation-backed predecessor contract and every later replayable record proves continuity using the signed predecessor fields
- **THEN** the structured replay result SHALL classify the chain or affected entries as supported reservation-backed replay rather than as degraded or invalid

#### Scenario: Legacy-to-reservation boundary is classified as degraded migration state
- **WHEN** immutable-backend replay encounters a chain segment whose earlier history uses legacy linkage semantics and whose later history uses the reservation-backed signed predecessor contract
- **THEN** the structured replay result SHALL preserve a machine-readable boundary classification for that mixed-regime boundary and SHALL NOT collapse it into a generic predecessor mismatch

#### Scenario: Reservation-to-legacy regression is classified as invalid
- **WHEN** immutable-backend replay encounters a record that reverts to incompatible legacy linkage semantics after the chain has already entered the reservation-backed signed predecessor regime
- **THEN** the structured replay result SHALL classify that boundary as an invalid regression rather than as merely degraded migration state

### Requirement: Public Rekor integration covers multi-entry predecessor proof
The immutable-backend verification capability SHALL include real-Rekor integration coverage for a multi-entry replayable chain that exercises public candidate discovery, candidate materialization, and signed predecessor matching across more than one record.

#### Scenario: Real Rekor test proves predecessor across multiple entries
- **WHEN** the real-Rekor integration suite verifies a replayable chain containing Event Log 0 and at least one later reservation-backed record
- **THEN** the suite SHALL assert that public candidate discovery resolves the predecessor from `prev_lookup_hash` and that the signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` contract is proven across more than one Rekor entry

#### Scenario: Real Rekor test does not rely on process-local predecessor cache truth
- **WHEN** the real-Rekor integration suite validates predecessor continuity
- **THEN** the proof assertion SHALL be based on immutable-backend candidate discovery and normalized replay entries rather than on process-local cache adjacency alone

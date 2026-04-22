## Purpose

Define the immutable-backend replay verification requirements exposed by `TrustedLogAPI.verify_record()`, including structured output and signed predecessor continuity.

## Requirements

### Requirement: Structured immutable-backend verification details
`TrustedLogAPI.verify_record()` SHALL return structured immutable-backend verification details that can be consumed by operator tooling. For replayable records, those details SHALL include predecessor-proof data such as whether signed continuity succeeded, how many predecessor candidates were discovered, how many candidates were materialized into replayable entries, how many candidates matched the signed predecessor contract, and whether candidate discovery failed independently from payload-proof mismatch.

#### Scenario: Verification result includes per-entry details
- **WHEN** immutable-backend replay verification finds one or more entries for the requested chain
- **THEN** the verification result SHALL include per-entry detail for each replayed immutable-backend record rather than only aggregate success metadata

#### Scenario: Verification result preserves source-specific failures
- **WHEN** immutable-backend replay verification encounters a digest mismatch, signer mismatch, traversal failure, or missing entries
- **THEN** the verification result SHALL report those failures in structured form so callers can render them without re-parsing exception text

#### Scenario: Verification result reports candidate pipeline counts
- **WHEN** immutable-backend replay verification produces a structured result for a replayed record with a non-null `prev_lookup_hash`
- **THEN** that result SHALL distinguish at least `candidate_count`, `materialized_candidate_count`, and `matched_candidate_count` rather than compressing the predecessor pipeline into a single count value

#### Scenario: Verification result reports predecessor status classification
- **WHEN** immutable-backend replay verification emits per-record predecessor detail
- **THEN** that result SHALL include `predecessor_status` and SHALL distinguish at least `origin`, `proven`, `missing`, `ambiguous`, `unverifiable`, `lookup_failed`, and `decode_failed` without requiring callers to infer those states from free-form error text

#### Scenario: Verification result preserves normalized candidate facts
- **WHEN** immutable-backend replay verification emits candidate-level diagnostics
- **THEN** each emitted candidate detail SHALL be limited to normalized factual fields such as `entry_id`, `chain_id`, `sequence_num`, `digest`, `payload_hash`, and decode or selection diagnostics rather than backend-native entry bodies

### Requirement: Immutable-backend verification policy inputs
`TrustedLogAPI.verify_record()` SHALL support policy inputs needed by operator verification tooling.

#### Scenario: Signer identity constraint
- **WHEN** verification is invoked with a signer identity policy
- **THEN** immutable-backend replay verification SHALL filter or fail according to that identity constraint and SHALL report the applied identity in structured output

#### Scenario: Expected entry count constraint
- **WHEN** verification is invoked with an expected entry count policy
- **THEN** immutable-backend replay verification SHALL report the observed entry count in structured output so callers can enforce that policy deterministically

### Requirement: Immutable-backend verification remains distinct from RTMR verification
Immutable-backend replay verification SHALL continue to exclude RTMR ordering proof from its own responsibility.

#### Scenario: Caller requests immutable-backend verification
- **WHEN** `TrustedLogAPI.verify_record()` completes successfully
- **THEN** its result SHALL represent immutable-backend replay findings without claiming to perform RTMR ordering verification that belongs to TruCon local chain verification

### Requirement: Immutable replay verifies signed predecessor continuity
`TrustedLogAPI.verify_record()` SHALL verify predecessor continuity for replayable records using the signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` fields carried in each replayed payload. Rekor or immutable-backend lookup SHALL be used only to discover predecessor candidates and SHALL NOT be treated as protocol truth on its own. Candidate proof SHALL be evaluated only against normalized replay entries rather than directly against backend-native entry bodies.

#### Scenario: Matching predecessor candidate proves continuity
- **WHEN** replay verification resolves one or more predecessor candidates from `prev_lookup_hash`, materializes them into replayable entries, and finds exactly one candidate whose `chain_id`, `sequence_num`, and recomputed event digest match the current record's signed predecessor fields
- **THEN** the record SHALL be reported with `predecessor_ok: true` and `predecessor_status: "proven"`

#### Scenario: No usable predecessor candidate is discovered
- **WHEN** replay verification cannot discover any usable predecessor candidate for a record whose signed predecessor contract requires lookup
- **THEN** the verification result SHALL report predecessor continuity failure as `predecessor_status: "missing"` or `predecessor_status: "lookup_failed"` as appropriate rather than as a generic mismatch

#### Scenario: Candidate decode failure remains distinct from proof mismatch

- **WHEN** replay verification discovers one or more predecessor candidates but cannot normalize any candidate into a replayable entry
- **THEN** the verification result SHALL report `predecessor_status: "decode_failed"`, SHALL preserve the discovered `candidate_count`, and SHALL report `materialized_candidate_count: 0`

#### Scenario: Multiple matching predecessor candidates are ambiguous
- **WHEN** replay verification materializes predecessor candidates and more than one candidate satisfies the signed predecessor contract
- **THEN** the verification result SHALL report `predecessor_ok: false`, `predecessor_status: "ambiguous"`, and `matched_candidate_count` greater than `1`

#### Scenario: Event Log 0 uses explicit null predecessor semantics
- **WHEN** replay verification evaluates Event Log 0 with `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`
- **THEN** the verifier SHALL treat that record as the valid replay origin for the chain, SHALL report `predecessor_ok: true`, and SHALL report `predecessor_status: "origin"`

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

### Requirement: Immutable replay can materialize predecessor bundles from a mirror
`TrustedLogAPI.verify_record()` SHALL support mirror-backed predecessor materialization for newly written replayable nodes when public immutable-log entry data does not contain enough payload material to reconstruct a replayable predecessor entry on its own.

#### Scenario: Mirror-backed materialization proves predecessor continuity
- **WHEN** replay verification cannot recover a replayable predecessor payload from public immutable-log entry data alone but a configured mirror resolves a `bundle.json` for the required `payload_hash`
- **THEN** the verifier SHALL normalize the mirrored bundle into replayable predecessor facts and SHALL evaluate signed predecessor continuity against that normalized material

#### Scenario: Mirror-required policy rejects missing mirrored content
- **WHEN** replay verification runs with a mirror-required policy and the required mirrored bundle cannot be resolved for a `payload_hash`
- **THEN** the verifier SHALL report predecessor proof as incomplete, degraded, or failed according to structured policy output rather than silently falling back to cache-only reconstruction

### Requirement: Immutable replay reports materialization provenance
`TrustedLogAPI.verify_record()` SHALL preserve machine-readable provenance that distinguishes public immutable-log materialization from mirror-backed materialization when replay verification reports historical continuity results.

#### Scenario: Structured replay result marks mirrored materialization
- **WHEN** replay verification succeeds using a mirrored predecessor bundle
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from the mirror rather than from public immutable-log entry data alone

#### Scenario: Structured replay result preserves public-only state
- **WHEN** replay verification reaches the requested head without using mirrored bundle material
- **THEN** the structured immutable-backend result SHALL preserve that replay state as public-only rather than conflating it with mirrored replay success

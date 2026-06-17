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
`TrustedLogAPI.verify_record()` SHALL support mirror-backed predecessor materialization for newly written replayable nodes when public immutable-log entry data and Rekor attestation storage do not contain enough payload material to reconstruct a replayable predecessor entry on their own.

#### Scenario: Mirror-backed materialization proves predecessor continuity
- **WHEN** replay verification cannot recover a replayable predecessor payload from public immutable-log entry data or Rekor attestation storage alone but a configured mirror resolves a `bundle.json` for the required `payload_hash`
- **THEN** the verifier SHALL normalize the mirrored bundle into replayable predecessor facts and SHALL evaluate signed predecessor continuity against that normalized material

#### Scenario: Mirror-required policy rejects missing mirrored content
- **WHEN** replay verification runs with a mirror-required policy and the required mirrored bundle cannot be resolved for a `payload_hash`
- **THEN** the verifier SHALL report predecessor proof as incomplete, degraded, or failed according to structured policy output rather than silently falling back to cache-only reconstruction

### Requirement: Immutable replay reports materialization provenance
`TrustedLogAPI.verify_record()` SHALL preserve machine-readable provenance that distinguishes public immutable-log materialization, Rekor attestation-storage materialization, and mirror-backed materialization when replay verification reports historical continuity results.

#### Scenario: Structured replay result marks mirrored materialization
- **WHEN** replay verification succeeds using a mirrored predecessor bundle
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from the mirror rather than from public immutable-log entry data alone

#### Scenario: Structured replay result marks attestation-storage materialization
- **WHEN** replay verification succeeds using payload material recovered from Rekor attestation storage
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from `attestation-storage` rather than from public body fields or OCI mirror

#### Scenario: Structured replay result preserves public-only state
- **WHEN** replay verification reaches the requested head without using mirrored bundle material or attestation-storage materialization
- **THEN** the structured immutable-backend result SHALL preserve that replay state as public-only rather than conflating it with mirrored or attestation-backed replay success

### Requirement: Immutable replay materializes payload facts from Rekor attestation storage
`TrustedLogAPI.verify_record()` SHALL materialize replayable payload facts from Rekor attestation storage when the public immutable-log body is not sufficient on its own.

#### Scenario: Attestation-backed candidate is normalized for predecessor verification
- **WHEN** predecessor candidate discovery returns a Rekor entry whose public body is hash-only but whose retrieval response contains attestation material that matches the entry's committed payload hash
- **THEN** immutable replay SHALL normalize that attestation into replayable predecessor facts and SHALL include the candidate in signed predecessor verification

#### Scenario: Invalid attestation material is rejected
- **WHEN** a retrieved attestation payload does not match the committed payload hash recorded by the immutable-log entry
- **THEN** immutable replay SHALL reject that attestation material for proof purposes and SHALL continue with remaining valid candidates or report failure if none remain

### Requirement: Immutable-backend verification proves accepted head entry inclusion
`TrustedLogAPI.verify_record()` SHALL require proof that the accepted Rekor-backed `head_log_id` was integrated into a signed Rekor tree state. Entry readback, payload decode, or replay continuity alone SHALL NOT be treated as sufficient proof of transparency-log inclusion for the accepted head entry.

#### Scenario: Accepted head entry is inclusion-verified
- **WHEN** immutable-backend verification accepts a Rekor-backed `head_log_id` and retrieves valid inclusion proof material for that entry
- **THEN** the verification result SHALL report that the accepted head entry was proven to belong to the corresponding signed Rekor tree state

#### Scenario: Entry readback without proof remains insufficient
- **WHEN** immutable-backend verification can read the accepted head entry body but cannot produce valid inclusion proof for that entry
- **THEN** the verification result SHALL NOT report the accepted head entry as log-inclusion-verified

### Requirement: Immutable-backend verification validates head checkpoint trust
`TrustedLogAPI.verify_record()` SHALL validate the signed checkpoint or equivalent signed tree head associated with the accepted head entry's inclusion proof before treating the accepted head entry as transparency-log verified.

#### Scenario: Checkpoint signature validation succeeds
- **WHEN** immutable-backend verification retrieves the checkpoint material associated with the accepted head entry's inclusion proof and the checkpoint signature validates against the configured trust source
- **THEN** the verification result SHALL report checkpoint trust as verified for that accepted head entry

#### Scenario: Checkpoint validation failure rejects head log verification
- **WHEN** immutable-backend verification retrieves checkpoint material for the accepted head entry but the checkpoint signature is invalid or does not chain to the configured trust source
- **THEN** the verification result SHALL report head log verification failure rather than degrading that result to successful inclusion

### Requirement: Immutable-backend verification reports explicit head log-verification states
`TrustedLogAPI.verify_record()` SHALL distinguish successful head-entry inclusion verification, degraded proof unavailability, and hard proof failure in structured output so callers can separate transparency-log assurance from replay continuity.

#### Scenario: Proof material unavailable yields degraded state
- **WHEN** immutable-backend verification establishes replay continuity for the accepted head entry but cannot retrieve enough inclusion proof or checkpoint material to complete head log verification
- **THEN** the verification result SHALL report the head log-verification dimension as degraded or incomplete rather than as successful

#### Scenario: Proof contradiction yields failed state
- **WHEN** immutable-backend verification detects that inclusion proof evaluation or checkpoint validation for the accepted head entry is cryptographically invalid
- **THEN** the verification result SHALL report the head log-verification dimension as failed

### Requirement: Immutable-backend verification supports explicit checkpoint bootstrap trust
`TrustedLogAPI.verify_record()` SHALL support an explicit initial trust source for validating the accepted head entry's checkpoint material when no previously trusted checkpoint is available.

#### Scenario: First trusted checkpoint uses bootstrap source
- **WHEN** immutable-backend verification runs without any previously trusted checkpoint state and a configured bootstrap trust source is available
- **THEN** the verifier SHALL use that bootstrap trust source to validate the accepted head entry's checkpoint material

#### Scenario: Bootstrap trust does not imply historical consistency proof
- **WHEN** immutable-backend verification succeeds for the accepted head entry using bootstrap checkpoint trust only
- **THEN** the result SHALL NOT claim that historical append-only consistency across time has been proven

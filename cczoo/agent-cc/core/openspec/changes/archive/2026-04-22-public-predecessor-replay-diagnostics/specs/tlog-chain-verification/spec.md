## MODIFIED Requirements

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
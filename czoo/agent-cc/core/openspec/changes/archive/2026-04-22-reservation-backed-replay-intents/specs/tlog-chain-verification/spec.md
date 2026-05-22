## ADDED Requirements

### Requirement: Immutable replay verifies signed predecessor continuity
`TrustedLogAPI.verify_record()` SHALL verify predecessor continuity for replayable records using the signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` fields carried in each replayed payload. Rekor or immutable-backend lookup SHALL be used only to discover predecessor candidates and SHALL NOT be treated as protocol truth on its own.

#### Scenario: Matching predecessor candidate proves continuity
- **WHEN** replay verification resolves one or more predecessor candidates from `prev_lookup_hash` and finds a candidate whose `chain_id`, `sequence_num`, and recomputed event digest match the current record's signed predecessor fields
- **THEN** the record SHALL be reported as having verified predecessor continuity

#### Scenario: Missing matching predecessor fails continuity
- **WHEN** replay verification cannot find any candidate whose replayed payload matches the current record's signed `prev_event_digest` and predecessor sequence contract
- **THEN** the verification result SHALL report predecessor continuity failure for that record

#### Scenario: Event Log 0 uses explicit null predecessor semantics
- **WHEN** replay verification evaluates Event Log 0 with `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`
- **THEN** the verifier SHALL treat that record as the valid replay origin for the chain rather than attempting predecessor lookup

### Requirement: Structured immutable-backend verification details expose predecessor proof data
`TrustedLogAPI.verify_record()` SHALL return structured immutable-backend verification details for predecessor continuity, including whether predecessor proof succeeded, how many candidates were examined, and whether candidate discovery failed independently from payload-proof mismatch.

#### Scenario: Verification result reports candidate discovery separately from proof result
- **WHEN** immutable-backend replay verification produces a structured result for a replayed record
- **THEN** that result SHALL distinguish between lookup failure, multiple-candidate discovery, and signed predecessor proof mismatch without requiring callers to infer those states from free-form error text
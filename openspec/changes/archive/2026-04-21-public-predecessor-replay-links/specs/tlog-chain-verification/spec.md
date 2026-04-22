## ADDED Requirements

### Requirement: Signed predecessor replay contract
`TrustedLogAPI.verify_record()` SHALL validate immutable-backend predecessor linkage using signed replay fields rather than public `prev_log_id` linkage.

#### Scenario: Verifier replays a non-baseline record
- **WHEN** immutable-backend replay evaluates a record whose signed predicate includes `chain_id`, `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`
- **THEN** the verifier SHALL treat those signed fields as the predecessor contract for that record

#### Scenario: Verifier replays Event Log 0
- **WHEN** immutable-backend replay evaluates a baseline record with `sequence_num = 1`
- **THEN** the verifier SHALL require `prev_event_digest = null` and `prev_lookup_hash = null` for that record's predecessor contract

### Requirement: Rekor lookup is candidate discovery only
`TrustedLogAPI.verify_record()` SHALL use Rekor search as a candidate-discovery step rather than as the source of predecessor correctness.

#### Scenario: Lookup returns multiple candidates
- **WHEN** Rekor lookup by `prev_lookup_hash` returns more than one candidate entry
- **THEN** the verifier SHALL continue by filtering candidates using signed replay fields instead of accepting any candidate solely because it was returned by the index

#### Scenario: Lookup returns a candidate set
- **WHEN** Rekor lookup by `prev_lookup_hash` returns one or more candidate entries
- **THEN** the verifier SHALL require a candidate whose `chain_id` matches, whose `sequence_num` equals `current.sequence_num - 1`, and whose recomputed `event_digest` equals `prev_event_digest`

#### Scenario: Lookup does not yield a valid predecessor
- **WHEN** Rekor lookup by `prev_lookup_hash` returns no candidate that satisfies the signed predecessor constraints
- **THEN** immutable-backend replay SHALL fail predecessor verification for that record and SHALL report the failure in structured verification output

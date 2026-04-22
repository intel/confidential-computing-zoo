## MODIFIED Requirements

### Requirement: Detailed per-entry verification response
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `prev_event_digest_ok` (bool|null), `prev_lookup_candidates` (int|null), and optionally `error` (str)

## REMOVED Requirements

### Requirement: prev_log_id linkage verification in non-TEE mode
**Reason**: Public predecessor proof now uses signed replay fields (`sequence_num`, `prev_event_digest`, and `prev_lookup_hash`) rather than non-TEE `prev_log_id` linkage.
**Migration**: Replace non-TEE predecessor checks with signed predecessor verification based on Rekor candidate discovery and digest confirmation.

## ADDED Requirements

### Requirement: Signed predecessor continuity verification
When `GET /verify-chain/{chain_id}` verifies public predecessor continuity, it SHALL use `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` instead of public `prev_log_id` linkage.

#### Scenario: Valid predecessor continuity
- **WHEN** a confirmed non-baseline record has a signed `prev_lookup_hash` that yields a predecessor candidate whose `sequence_num` is exactly one less and whose recomputed event digest matches `prev_event_digest`
- **THEN** that entry SHALL report `prev_event_digest_ok: true`

#### Scenario: Baseline record has null predecessor
- **WHEN** the first record in the chain is Event Log 0 with `sequence_num = 1`
- **THEN** that entry SHALL report `prev_event_digest_ok: true` when both `prev_event_digest` and `prev_lookup_hash` are null

#### Scenario: Multiple lookup candidates require digest confirmation
- **WHEN** Rekor lookup by `prev_lookup_hash` returns multiple predecessor candidates
- **THEN** the endpoint SHALL require a candidate whose `sequence_num` and recomputed event digest satisfy the signed predecessor contract before reporting predecessor continuity success

#### Scenario: No valid predecessor candidate
- **WHEN** Rekor lookup by `prev_lookup_hash` yields no candidate that satisfies the signed predecessor contract
- **THEN** that entry SHALL report `prev_event_digest_ok: false`, SHALL describe the mismatch in `error`, and the top-level `valid` SHALL be `false`

### Requirement: Predecessor lookup reporting is best-effort
The `/verify-chain/{chain_id}` response SHALL expose candidate-discovery results without treating Rekor index search completeness or uniqueness as protocol truth.

#### Scenario: Candidate count is reported
- **WHEN** the endpoint performs predecessor lookup for a confirmed non-baseline record
- **THEN** the entry SHALL include `prev_lookup_candidates` with the number of candidates returned by candidate discovery

#### Scenario: Pending or unconfirmed record cannot perform lookup
- **WHEN** a record is not yet confirmed in the immutable backend
- **THEN** that entry SHALL report `prev_event_digest_ok: null` and `prev_lookup_candidates: null`

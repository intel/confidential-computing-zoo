## MODIFIED Requirements

### Requirement: Detailed per-entry verification response
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail. For reservation-backed replayable records, the per-entry detail SHALL expose predecessor-continuity verification using signed replay fields rather than `prev_log_id` linkage.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `predecessor_ok` (bool|null), `prev_event_digest` (str|null), `prev_lookup_hash` (str|null), and optionally `candidate_count` (int|null) and `error` (str)

## REMOVED Requirements

### Requirement: prev_log_id linkage verification in non-TEE mode
**Reason**: Reservation-backed replay replaces backend-assigned `prev_log_id` linkage with signed predecessor proof using `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`.
**Migration**: Verify predecessor continuity through the signed replay fields and expose the result as `predecessor_ok` rather than `prev_log_id_ok`.

## ADDED Requirements

### Requirement: Signed predecessor continuity verification
When evaluating replayable records, `GET /verify-chain/{chain_id}` SHALL verify predecessor continuity using the signed predecessor contract persisted with each queue record. The verification logic SHALL treat immutable-backend lookup as candidate discovery and SHALL report predecessor status independently from RTMR availability.

#### Scenario: Valid signed predecessor chain in non-TEE mode
- **WHEN** `GET /verify-chain/{chain_id}` is called in a non-TEE environment and each confirmed record's signed predecessor contract matches the prior replayed record
- **THEN** each verified entry SHALL report `predecessor_ok: true`

#### Scenario: Baseline record uses null predecessor contract
- **WHEN** the first record in the chain is Event Log 0 with `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`
- **THEN** that entry SHALL report `predecessor_ok: true`

#### Scenario: Predecessor mismatch detected
- **WHEN** a confirmed record's signed predecessor fields do not match any valid predecessor candidate for the prior sequence position
- **THEN** that entry SHALL have `predecessor_ok: false`, `error` SHALL describe the mismatch, and top-level `valid` SHALL be `false`

#### Scenario: Unconfirmed record cannot prove predecessor yet
- **WHEN** a record has not yet been confirmed in the immutable backend and predecessor replay cannot be completed
- **THEN** that entry SHALL have `predecessor_ok: null` and MAY report candidate discovery as unavailable
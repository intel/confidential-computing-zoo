## ADDED Requirements

### Requirement: prev_log_id linkage verification in non-TEE mode
When `rtmr_available` is `false`, the `GET /verify-chain/{chain_id}` endpoint SHALL verify `prev_log_id` linkage for each confirmed record. For each record (ordered by `sequence_num`), the endpoint SHALL check that `prev_log_id` matches the `log_id` of the preceding confirmed record. When `rtmr_available` is `true`, the `prev_log_id` check SHALL be skipped and `prev_log_id_ok` SHALL be `null` for all entries.

#### Scenario: Valid prev_log_id chain in non-TEE mode
- **WHEN** `GET /verify-chain/default` is called with `rtmr_available == false` and all confirmed records have `prev_log_id` matching the preceding record's `log_id`
- **THEN** each verified entry SHALL have `prev_log_id_ok: true`

#### Scenario: First record has null prev_log_id
- **WHEN** the first record in the chain has `prev_log_id = NULL` (no predecessor)
- **THEN** that entry SHALL have `prev_log_id_ok: true`

#### Scenario: prev_log_id mismatch detected
- **WHEN** a confirmed record's `prev_log_id` does not match the preceding confirmed record's `log_id`
- **THEN** that entry SHALL have `prev_log_id_ok: false` and `error` SHALL describe the mismatch, and top-level `valid` SHALL be `false`

#### Scenario: Unconfirmed record in chain
- **WHEN** a record has `log_id = NULL` (not yet confirmed by immutable backend)
- **THEN** that entry SHALL have `prev_log_id_ok: null` (cannot verify)

#### Scenario: RTMR available suppresses prev_log_id check
- **WHEN** `GET /verify-chain/default` is called with `rtmr_available == true`
- **THEN** every entry SHALL have `prev_log_id_ok: null` regardless of `prev_log_id` values

### Requirement: Non-TEE startup warning
When TDX RTMR sysfs is not detected at startup, TruCon SHALL emit a `WARNING`-level log message with "NON-TEE MODE" in the text, indicating that the instance is running without hardware measurement extensions and is suitable for development/testing only.

#### Scenario: Startup without TDX hardware
- **WHEN** TruCon starts and `/sys/class/misc/tdx_guest/measurements/rtmr` does not exist
- **THEN** a `WARNING`-level log message SHALL be emitted containing "NON-TEE MODE"

#### Scenario: Startup with TDX hardware
- **WHEN** TruCon starts and `/sys/class/misc/tdx_guest/measurements/rtmr` exists
- **THEN** no "NON-TEE MODE" warning SHALL be emitted

## MODIFIED Requirements

### Requirement: Detailed per-entry verification response
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `prev_log_id_ok` (bool|null), and optionally `error` (str)

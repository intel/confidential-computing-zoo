## ADDED Requirements

### Requirement: event_digest persistence in commit_queue
The TruCon `/commit` endpoint SHALL persist the `event_digest` field from the commit request into the `commit_queue` SQLite table. The column SHALL be `event_digest TEXT` and SHALL contain the SHA-384 hex digest string (prefixed `sha384:`).

#### Scenario: event_digest stored on commit
- **WHEN** TruCon receives a `POST /commit` request with `event_digest: "sha384:abcd..."`
- **THEN** the resulting `commit_queue` row SHALL have `event_digest = "sha384:abcd..."`

#### Scenario: Pre-migration rows have NULL event_digest
- **WHEN** the `commit_queue` table contains rows created before the `event_digest` column was added
- **THEN** those rows SHALL have `event_digest = NULL`

### Requirement: Full chain traversal via GET /verify-chain/{chain_id}
TruCon SHALL expose a `GET /verify-chain/{chain_id}` endpoint that reads all `commit_queue` records for the given `chain_id`, ordered by `sequence_num`, and verifies sequence continuity, RTMR chain integrity, and Rekor confirmation status.

#### Scenario: Verify a valid chain
- **WHEN** a client calls `GET /verify-chain/default` and all records have contiguous sequence numbers, valid RTMR extends, and confirmed Rekor status
- **THEN** the response SHALL have `valid: true` with all entries showing `mr_ok: true` and `rekor_ok: true`

#### Scenario: Chain with RTMR mismatch
- **WHEN** a record's `mr_value` does not equal `SHA384(prev_mr_value || event_digest)`
- **THEN** that entry SHALL have `mr_ok: false` and `error` describing the mismatch, and the top-level `valid` SHALL be `false`

#### Scenario: Chain with sequence gap
- **WHEN** sequence numbers are non-contiguous (e.g., 1, 2, 4)
- **THEN** the entry at the gap SHALL have `error: "sequence gap: expected 3, got 4"` and `valid` SHALL be `false`

#### Scenario: Chain with pending Rekor submissions
- **WHEN** some records have `status != "CONFIRMED"` or `log_id IS NULL`
- **THEN** those entries SHALL have `rekor_ok: false` but this alone SHALL NOT set `valid: false` (pending submissions are expected)

#### Scenario: Non-existent chain_id
- **WHEN** `GET /verify-chain/nonexistent` is called and no records exist for that chain_id
- **THEN** the response SHALL return HTTP 404

### Requirement: Detailed per-entry verification response
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `prev_log_id_ok` (bool|null), and optionally `error` (str)

### Requirement: RTMR verification skipped in non-TDX environments
When all `mr_value` entries in the chain are `NULL`, the endpoint SHALL set `rtmr_available: false` and report `mr_ok: null` for every entry rather than failing.

#### Scenario: All mr_values are NULL
- **WHEN** `GET /verify-chain/default` is called and every record has `mr_value = NULL`
- **THEN** the response SHALL have `rtmr_available: false` and every entry SHALL have `mr_ok: null`

#### Scenario: Mixed NULL and non-NULL mr_values
- **WHEN** some records have `mr_value = NULL` and others have values (partially migrated data)
- **THEN** entries with `NULL mr_value` SHALL have `mr_ok: null` and entries with values SHALL be verified normally

### Requirement: NULL event_digest treated as RTMR check skipped
When a record has `event_digest = NULL` (pre-migration row), the RTMR chain check SHALL be skipped for that entry. The entry SHALL report `mr_ok: null` rather than `false`.

#### Scenario: Pre-migration entry in chain
- **WHEN** a record has `event_digest = NULL` but `mr_value` is present
- **THEN** that entry SHALL have `mr_ok: null` (skipped, not failed) and the chain SHALL continue verification from the next entry using this entry's `mr_value` as `prev_mr`

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

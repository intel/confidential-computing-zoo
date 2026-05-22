## Purpose

Define the structural and integrity verification requirements exposed by TruCon for replaying and validating per-chain state.
## Requirements
### Requirement: Non-default chains must begin with Event Log 0
`GET /verify-chain/{chain_id}` SHALL treat Event Log 0 as a structural prerequisite for every non-`default` chain. A non-`default` chain whose first record is not a baseline record SHALL be reported as invalid.

#### Scenario: Valid workload chain begins with baseline
- **WHEN** `GET /verify-chain/workload-a` is called and the first record in that chain is Event Log 0 followed by contiguous later records
- **THEN** the baseline-origin check SHALL pass and the chain's validity SHALL continue to depend on the remaining sequence, RTMR, and immutable-backend checks

#### Scenario: Workload chain missing baseline fails verification
- **WHEN** `GET /verify-chain/workload-a` is called and the first record in that non-`default` chain is a business or runtime event instead of Event Log 0
- **THEN** the response SHALL set `valid: false` and SHALL report the missing baseline as a structural verification error

#### Scenario: Pending baseline still satisfies origin requirement
- **WHEN** `GET /verify-chain/workload-a` is called and the first record is Event Log 0 but it is still pending immutable-backend confirmation
- **THEN** the chain SHALL satisfy the baseline-origin requirement even though the pending record still contributes to `rekor_pending`

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
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail. For reservation-backed replayable records, the per-entry detail SHALL expose predecessor-continuity verification using signed replay fields rather than `prev_log_id` linkage, SHALL preserve the same predecessor result vocabulary used by immutable replay verification, and SHALL additionally report owner-authorization verification for chains whose Event Log 0 declares a single owner key.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `predecessor_ok` (bool|null), `predecessor_status` (str|null), `prev_event_digest` (str|null), `prev_lookup_hash` (str|null), `owner_ok` (bool|null), `owner_status` (str|null), and optionally `candidate_count` (int|null), `materialized_candidate_count` (int|null), `matched_candidate_count` (int|null), `boundary_status` (str|null), and `error` (str)

#### Scenario: Entry distinguishes proof pipeline stages
- **WHEN** a replayable entry includes predecessor verification detail
- **THEN** the serialized entry SHALL preserve enough candidate-pipeline detail to distinguish candidate discovery failure, decode failure, no-match proof failure, and ambiguity without requiring callers to parse free-form error text

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

### Requirement: Signed predecessor continuity verification
When evaluating replayable records, `GET /verify-chain/{chain_id}` SHALL verify predecessor continuity using the signed predecessor contract persisted with each queue record. The verification logic SHALL treat immutable-backend lookup as candidate discovery, SHALL report predecessor status independently from RTMR availability, SHALL classify replay regime boundaries separately from ordinary predecessor mismatch, and SHALL report owner-authorization verification independently from predecessor continuity.

#### Scenario: Valid signed predecessor chain in non-TEE mode
- **WHEN** `GET /verify-chain/{chain_id}` is called in a non-TEE environment and each confirmed record's signed predecessor contract matches exactly one normalized predecessor candidate
- **THEN** each verified entry SHALL report `predecessor_ok: true` and `predecessor_status: "proven"`

#### Scenario: Baseline record uses null predecessor contract
- **WHEN** the first record in the chain is Event Log 0 with `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`
- **THEN** that entry SHALL report `predecessor_ok: true` and `predecessor_status: "origin"`

#### Scenario: Predecessor mismatch detected
- **WHEN** a confirmed record's signed predecessor fields do not match any valid predecessor candidate for the prior sequence position after candidate materialization
- **THEN** that entry SHALL have `predecessor_ok: false`, `predecessor_status: "missing"` or another more specific failure classification, `error` SHALL describe the failure, and top-level `valid` SHALL be `false`

#### Scenario: Unconfirmed record cannot prove predecessor yet
- **WHEN** a record has not yet been confirmed in the immutable backend and predecessor replay cannot be completed
- **THEN** that entry SHALL have `predecessor_ok: null` and `predecessor_status: "unverifiable"`

#### Scenario: Mixed replay regimes remain visible to operators
- **WHEN** verification encounters a boundary between reservation-backed replay semantics and an incompatible legacy replay regime
- **THEN** the response SHALL preserve a machine-readable `boundary_status` classification rather than reporting only a generic predecessor mismatch for the boundary entry

### Requirement: Verification SHALL check owner-key continuity for replayable records
For chains whose Event Log 0 declares a single owner key, verification SHALL determine whether each confirmed replayable record remains authorized by that owner key and SHALL report the result independently from predecessor continuity.

#### Scenario: Confirmed record proves owner authorization
- **WHEN** a confirmed replayable record carries authorization that validates against the owner public key declared at Event Log 0
- **THEN** verification SHALL report `owner_ok: true` and `owner_status: "proven"` for that record

#### Scenario: Confirmed record fails owner authorization
- **WHEN** a confirmed replayable record cannot be validated against the owner public key declared at Event Log 0
- **THEN** verification SHALL report `owner_ok: false`, SHALL populate `owner_status` with a machine-readable failure classification, and SHALL mark the chain invalid

#### Scenario: Pending record is owner-unverifiable
- **WHEN** a replayable record has not yet been confirmed or cannot yet be replayed with sufficient authorization material
- **THEN** verification SHALL report `owner_ok: null` and `owner_status: "unverifiable"` rather than forcing an owner failure

### Requirement: TruCon classifies replay rollout boundaries
`GET /verify-chain/{chain_id}` SHALL preserve rollout-boundary classifications for mixed legacy and reservation-backed replay regimes so operators can distinguish degraded migration state from invalid regression. These classifications SHALL remain machine-readable and SHALL be exposed independently from RTMR availability.

#### Scenario: Legacy boundary is reported as degraded migration state
- **WHEN** chain verification encounters a boundary from legacy predecessor linkage into the reservation-backed signed predecessor regime
- **THEN** the response SHALL preserve a machine-readable boundary classification for the affected entry or summary and SHALL identify that boundary as degraded migration state rather than as a generic predecessor mismatch

#### Scenario: Regression after reservation-backed entry is reported as invalid
- **WHEN** chain verification encounters a regression into incompatible legacy predecessor linkage after a chain has already produced reservation-backed replayable records
- **THEN** the response SHALL preserve a machine-readable boundary classification that marks the regression as invalid rather than as degraded migration state

#### Scenario: Boundary classification survives non-TEE verification
- **WHEN** TruCon verifies a chain in non-TEE mode and a replay-regime boundary is present
- **THEN** the response SHALL preserve the same machine-readable boundary classification even if `mr_ok` is unavailable or skipped for some entries

### Requirement: Non-TEE startup warning
When TDX RTMR sysfs is not detected at startup, TruCon SHALL emit a `WARNING`-level log message with "NON-TEE MODE" in the text, indicating that the instance is running without hardware measurement extensions and is suitable for development/testing only.

#### Scenario: Startup without TDX hardware
- **WHEN** TruCon starts and `/sys/class/misc/tdx_guest/measurements/rtmr` does not exist
- **THEN** a `WARNING`-level log message SHALL be emitted containing "NON-TEE MODE"

#### Scenario: Startup with TDX hardware
- **WHEN** TruCon starts and `/sys/class/misc/tdx_guest/measurements/rtmr` exists
- **THEN** no "NON-TEE MODE" warning SHALL be emitted

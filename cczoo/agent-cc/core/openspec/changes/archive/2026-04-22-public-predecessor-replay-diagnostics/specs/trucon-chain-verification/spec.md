## MODIFIED Requirements

### Requirement: Detailed per-entry verification response
The `/verify-chain/{chain_id}` response SHALL include a top-level summary and an `entries` array with per-entry detail. For reservation-backed replayable records, the per-entry detail SHALL expose predecessor-continuity verification using signed replay fields rather than `prev_log_id` linkage, and SHALL preserve the same predecessor result vocabulary used by immutable replay verification.

#### Scenario: Response structure
- **WHEN** the verification endpoint returns a result
- **THEN** the response SHALL contain: `valid` (bool), `chain_id` (str), `total_entries` (int), `mr_verified` (int), `rekor_confirmed` (int), `rekor_pending` (int), `rtmr_available` (bool), `head_mr_value` (str|null), `first_error_at` (int|null), and `entries` (array)

#### Scenario: Entry structure
- **WHEN** each entry in the `entries` array is serialized
- **THEN** it SHALL contain: `seq` (int), `record_id` (str), `event_id` (str), `mr_ok` (bool|null), `rekor_ok` (bool), `rtmr_extended` (bool), `mr_value` (str|null), `predecessor_ok` (bool|null), `predecessor_status` (str|null), `prev_event_digest` (str|null), `prev_lookup_hash` (str|null), and optionally `candidate_count` (int|null), `materialized_candidate_count` (int|null), `matched_candidate_count` (int|null), `boundary_status` (str|null), and `error` (str)

#### Scenario: Entry distinguishes proof pipeline stages
- **WHEN** a replayable entry includes predecessor verification detail
- **THEN** the serialized entry SHALL preserve enough candidate-pipeline detail to distinguish candidate discovery failure, decode failure, no-match proof failure, and ambiguity without requiring callers to parse free-form error text

### Requirement: Signed predecessor continuity verification
When evaluating replayable records, `GET /verify-chain/{chain_id}` SHALL verify predecessor continuity using the signed predecessor contract persisted with each queue record. The verification logic SHALL treat immutable-backend lookup as candidate discovery, SHALL report predecessor status independently from RTMR availability, and SHALL classify replay regime boundaries separately from ordinary predecessor mismatch.

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
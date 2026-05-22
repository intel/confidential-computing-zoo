## MODIFIED Requirements

### Requirement: Lossy Crash Recovery
The queue SHALL perform conditional crash recovery on Trust API startup. Records with `rtmr_extended=TRUE` and `status=PENDING` SHALL be retained for Rekor submission. Records with `rtmr_extended=FALSE` SHALL be deleted. The `chain_state` table SHALL be rebuilt from the highest `sequence_num` record with `rtmr_extended=TRUE`. Upon VM reboot (implied by `/dev/shm` reset), all queue data vanishes, retaining cryptographic validity on subsequent commits because RTMR registers also reset.

#### Scenario: Submitting event post-crash
- **WHEN** the VM completely restarts and initiates the hardware TD bounds anew
- **THEN** previous uncommitted local events vanish cryptographically, retaining 100% cryptographic validity logic on subsequent commits

#### Scenario: Process restart with RTMR-extended pending records
- **WHEN** the Trust API process restarts (not VM reboot) and finds records with `rtmr_extended=TRUE` and `status=PENDING`
- **THEN** those records SHALL be retained in the queue for the submit daemon to process

#### Scenario: Process restart with non-extended records
- **WHEN** the Trust API process restarts and finds records with `rtmr_extended=FALSE`
- **THEN** those records SHALL be deleted from the queue

## ADDED Requirements

### Requirement: Extended commit_queue schema
The `commit_queue` table SHALL include the following columns: `record_id` (TEXT PRIMARY KEY), `event_id` (TEXT), `chain_id` (TEXT NOT NULL), `payload` (TEXT NOT NULL), `status` (TEXT NOT NULL), `rtmr_extended` (BOOLEAN DEFAULT FALSE), `log_id` (TEXT), `prev_log_id` (TEXT), `mr_value` (TEXT), `sequence_num` (INTEGER NOT NULL), `retry_count` (INTEGER DEFAULT 0), `confirmed_at` (TEXT), `updated_at` (TEXT NOT NULL).

#### Scenario: Record inserted with all required fields
- **WHEN** the Trust API inserts a commit record into the queue
- **THEN** the record SHALL include `chain_id`, `sequence_num`, and `rtmr_extended` fields in addition to existing fields

### Requirement: chain_state table
The database SHALL include a `chain_state` table with columns: `chain_id` (TEXT PRIMARY KEY), `head_record_id` (TEXT), `head_log_id` (TEXT), `sequence_num` (INTEGER DEFAULT 0), `mr_value` (TEXT), `updated_at` (TEXT NOT NULL). This table maintains one row per chain, tracking the current chain head.

#### Scenario: Chain state created on first commit
- **WHEN** a commit arrives for a `chain_id` that has no existing `chain_state` row
- **THEN** the system SHALL INSERT a new row with `sequence_num=1` and the commit's `record_id` as `head_record_id`

#### Scenario: Chain state updated on subsequent commit
- **WHEN** a commit arrives for a `chain_id` that already has a `chain_state` row
- **THEN** the system SHALL UPDATE the row with incremented `sequence_num`, new `head_record_id`, and new `mr_value`

### Requirement: Schema migration from legacy format
On first startup with an existing database, the Trust API SHALL detect the legacy schema (missing `rtmr_extended` column) and run `ALTER TABLE` to add new columns with appropriate defaults. The `chain_state` table SHALL be created if absent. Existing records SHALL receive `rtmr_extended=NULL` (treated as unknown and discarded during crash recovery).

#### Scenario: Migrate legacy database
- **WHEN** the Trust API starts and finds a `commit_queue` table without the `rtmr_extended` column
- **THEN** it SHALL add the missing columns and create the `chain_state` table without data loss to existing records

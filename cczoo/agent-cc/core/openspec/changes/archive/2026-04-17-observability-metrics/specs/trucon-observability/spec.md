## ADDED Requirements

### Requirement: commit_latency metric emission
The `/commit` handler SHALL emit a structured log line upon completion with `metric=commit_latency`, `latency_ms` (float, milliseconds elapsed from handler entry to response), `record_id`, and `idempotent` (bool, true if the response was served from the idempotency cache). The timing SHALL include lock wait time.

#### Scenario: Normal commit logs latency
- **WHEN** a POST /commit request completes successfully with a new record
- **THEN** a log line SHALL be emitted with `metric=commit_latency`, `latency_ms` reflecting total handler time, `record_id` set to the new record's ID, and `idempotent=false`

#### Scenario: Idempotent commit logs latency
- **WHEN** a POST /commit request hits the idempotency cache and returns a cached response
- **THEN** a log line SHALL be emitted with `metric=commit_latency`, `latency_ms` reflecting total handler time, and `idempotent=true`

### Requirement: idempotency_hit_count metric emission
The `/commit` handler SHALL emit a structured log line with `metric=idempotency_hit` whenever a duplicate idempotency key is detected and the cached response is returned. The log line SHALL include `key` (the idempotency key), `chain_id`, and `record_id` of the existing record.

#### Scenario: Duplicate key detected
- **WHEN** a POST /commit request provides an idempotency_key that matches an existing record
- **THEN** a log line SHALL be emitted with `metric=idempotency_hit`, `key`, `chain_id`, and `record_id`

### Requirement: submit_latency metric emission
The submit daemon SHALL emit a structured log line with `metric=submit_latency` after each record submission attempt. The log line SHALL include `latency_ms` (float, milliseconds from SUBMITTING mark to outcome), `record_id`, and `outcome` (one of `confirmed`, `failed_retryable`, `failed_terminal`).

#### Scenario: Successful submission logs latency
- **WHEN** the submit daemon confirms a record with the backend
- **THEN** a log line SHALL be emitted with `metric=submit_latency`, `outcome=confirmed`, and `latency_ms` reflecting time from `set_status_submitting()` to `update_record_confirmed()`

#### Scenario: Failed submission logs latency
- **WHEN** the submit daemon fails to submit a record and marks it FAILED_RETRYABLE
- **THEN** a log line SHALL be emitted with `metric=submit_latency`, `outcome=failed_retryable`, and `latency_ms`

### Requirement: queue_snapshot metric emission
The submit daemon SHALL emit a structured log line with `metric=queue_snapshot` at the end of each tick cycle. The log line SHALL include `queue_depth` (PENDING count), `submitting_count`, `failed_retryable_count`, `failed_terminal_count`, and `total_retry_count` (SUM of all retry_count values).

#### Scenario: Daemon tick emits snapshot
- **WHEN** the submit daemon completes a tick cycle
- **THEN** a log line SHALL be emitted with `metric=queue_snapshot` and all five count fields reflecting current database state

#### Scenario: Empty queue snapshot
- **WHEN** the commit queue has no records
- **THEN** the snapshot log line SHALL show all counts as 0

### Requirement: confirmation_lag metric emission
When a record transitions to CONFIRMED status, the system SHALL emit a structured log line with `metric=confirmation_lag`, `lag_ms` (float, milliseconds between `created_at` and `confirmed_at`), and `record_id`.

#### Scenario: Record confirmed logs lag
- **WHEN** `update_record_confirmed()` successfully confirms a record that has a `created_at` timestamp
- **THEN** a log line SHALL be emitted with `metric=confirmation_lag`, `lag_ms` computed as `confirmed_at - created_at` in milliseconds, and `record_id`

#### Scenario: Record without created_at skips lag
- **WHEN** a record is confirmed but `created_at` is NULL (pre-migration record that was not backfilled)
- **THEN** no `confirmation_lag` log line SHALL be emitted for that record

### Requirement: created_at column in commit_queue
The `commit_queue` table SHALL have a `created_at TEXT` column. New records inserted via `insert_record()` SHALL set `created_at` to the current UTC ISO 8601 timestamp at INSERT time. The `created_at` column SHALL NOT be updated on subsequent status changes. The migration SHALL add the column if missing and backfill existing rows with `created_at = updated_at`.

#### Scenario: New record has created_at set
- **WHEN** `insert_record()` creates a new record
- **THEN** the record's `created_at` SHALL be set to the current UTC time and SHALL NOT change on subsequent `update_status()` calls

#### Scenario: Migration adds column to existing table
- **WHEN** TruCon starts and `commit_queue` exists without a `created_at` column
- **THEN** the migration SHALL add `created_at TEXT` and execute `UPDATE commit_queue SET created_at = updated_at WHERE created_at IS NULL`

### Requirement: total_retry_count in queue stats
The `get_queue_stats()` function SHALL return a `total_retry_count` field containing `SUM(retry_count)` across all records in the commit queue.

#### Scenario: Stats include aggregate retry count
- **WHEN** the commit queue contains records with retry_count values of 3, 5, and 0
- **THEN** `get_queue_stats()` SHALL return `total_retry_count: 8`

#### Scenario: Empty queue returns zero retries
- **WHEN** the commit queue has no records
- **THEN** `get_queue_stats()` SHALL return `total_retry_count: 0`

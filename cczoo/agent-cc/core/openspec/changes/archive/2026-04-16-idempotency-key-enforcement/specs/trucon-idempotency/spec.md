## ADDED Requirements

### Requirement: TruCon detects duplicate commits by idempotency key
The TruCon `POST /commit` endpoint SHALL accept an optional `idempotency_key` field in the request body. When a request includes an `idempotency_key` that matches an existing record in the same `chain_id`, TruCon SHALL return the original `CommitResponse` for that record without performing an RTMR extend, SQLite insert, or chain_state update.

#### Scenario: First commit with idempotency key
- **WHEN** TruCon receives a `POST /commit` with an `idempotency_key` that does not exist in `commit_queue`
- **THEN** TruCon SHALL proceed with the normal commit flow (RTMR extend, INSERT, chain_state update) and store the `idempotency_key` alongside the record

#### Scenario: Duplicate commit returns cached response
- **WHEN** TruCon receives a `POST /commit` with an `idempotency_key` that already exists in `commit_queue`
- **THEN** TruCon SHALL return the original `CommitResponse` (same `record_id`, `sequence_num`, `mr_value`, `prev_mr_value`) without performing RTMR extend or inserting a new record

#### Scenario: Duplicate commit matching a FAILED record
- **WHEN** TruCon receives a `POST /commit` with an `idempotency_key` matching a record with `status=FAILED`
- **THEN** TruCon SHALL return the FAILED record's data in the `CommitResponse` without re-attempting the commit

#### Scenario: Commit without idempotency key
- **WHEN** TruCon receives a `POST /commit` without an `idempotency_key` (field omitted or null)
- **THEN** TruCon SHALL proceed with the normal commit flow without deduplication

### Requirement: Idempotency check is atomic within the sequencer lock
The idempotency key lookup SHALL be performed inside `_sequencer_lock`, before the RTMR extend step. This SHALL prevent TOCTOU races where two concurrent requests with the same key both pass the check before either inserts.

#### Scenario: Concurrent identical requests serialize correctly
- **WHEN** two `POST /commit` requests with the same `idempotency_key` arrive concurrently
- **THEN** the first request to acquire `_sequencer_lock` SHALL perform the full commit; the second SHALL detect the duplicate and return the cached response

### Requirement: Idempotency key stored in commit_queue with UNIQUE constraint
The `commit_queue` table SHALL include an `idempotency_key TEXT` column with a `UNIQUE` constraint. Existing rows without an idempotency key SHALL have `NULL` in this column. SQLite's UNIQUE constraint SHALL allow multiple NULL values.

#### Scenario: Schema migration adds idempotency_key column
- **WHEN** TruCon starts with a legacy `commit_queue` table that lacks the `idempotency_key` column
- **THEN** the migration logic SHALL add the column via `ALTER TABLE ADD COLUMN idempotency_key TEXT UNIQUE`

#### Scenario: New database includes idempotency_key column
- **WHEN** TruCon initializes a fresh database
- **THEN** the `CREATE TABLE commit_queue` statement SHALL include `idempotency_key TEXT UNIQUE`

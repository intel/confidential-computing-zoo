## Purpose

Define the requirements for TruCon's embedded submit daemon, including lifecycle, retry handling, and ordering guarantees.

## Requirements

### Requirement: Background thread lifecycle
The submit daemon SHALL run as a `threading.Thread(daemon=True)` started during TruCon's FastAPI lifespan. The daemon SHALL transition records from `PENDING` to `SUBMITTING` before attempting backend submission. On successful submission, it SHALL transition to `CONFIRMED`. On transient failure, it SHALL transition to `FAILED_RETRYABLE` and increment `retry_count`. When `retry_count` reaches `MAX_RETRIES`, it SHALL transition from `FAILED_RETRYABLE` to `FAILED_TERMINAL`.

#### Scenario: Daemon marks SUBMITTING before submission
- **WHEN** the submit daemon picks up a PENDING record for submission
- **THEN** the record's status SHALL be updated to `SUBMITTING` before the backend call is made

#### Scenario: Successful submission confirms record
- **WHEN** the backend confirms the bundle submission
- **THEN** the record SHALL transition from `SUBMITTING` to `CONFIRMED` with `log_id` and `confirmed_at` populated

#### Scenario: Transient failure marks retryable
- **WHEN** the backend call fails and `retry_count < MAX_RETRIES`
- **THEN** the record SHALL transition from `SUBMITTING` to `FAILED_RETRYABLE` with `retry_count` incremented

#### Scenario: Retry threshold triggers terminal failure
- **WHEN** a record in `FAILED_RETRYABLE` has `retry_count >= MAX_RETRIES`
- **THEN** the record SHALL transition to `FAILED_TERMINAL`

### Requirement: Ordered Rekor submission
The submit daemon SHALL process records in `sequence_num` order within each chain. Records in `FAILED_TERMINAL` state SHALL block submission of subsequent records in the same chain. Records in `FAILED_RETRYABLE` state SHALL also block subsequent records (they will be retried first).

#### Scenario: FAILED_TERMINAL blocks chain
- **WHEN** a chain has a record in `FAILED_TERMINAL` state at sequence N
- **THEN** the daemon SHALL NOT submit any record with sequence > N in that chain

#### Scenario: FAILED_RETRYABLE blocks chain
- **WHEN** a chain has a record in `FAILED_RETRYABLE` state at sequence N
- **THEN** the daemon SHALL reset it to `PENDING` and process it before any record with sequence > N

## ADDED Requirements

### Requirement: Six-state lifecycle enum
The `SubmitStatus` enum SHALL define exactly six values: `OPEN`, `PENDING`, `SUBMITTING`, `CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`. The enum values SHALL be lowercase strings matching the state name (e.g., `"pending"`, `"failed_retryable"`).

#### Scenario: Enum contains all six states
- **WHEN** the `SubmitStatus` enum is inspected
- **THEN** it SHALL contain members: `OPEN`, `PENDING`, `SUBMITTING`, `CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL`

### Requirement: State transition rules
The system SHALL enforce the following valid state transitions: `PENDING → SUBMITTING` (daemon pickup), `SUBMITTING → CONFIRMED` (backend success), `SUBMITTING → FAILED_RETRYABLE` (transient failure), `FAILED_RETRYABLE → PENDING` (retry reset when retry_count < MAX_RETRIES), `FAILED_RETRYABLE → FAILED_TERMINAL` (retry_count >= MAX_RETRIES). `CONFIRMED` and `FAILED_TERMINAL` are terminal states — no transitions out.

#### Scenario: Successful submission flow
- **WHEN** the submit daemon picks up a PENDING record and the backend confirms
- **THEN** the record SHALL transition PENDING → SUBMITTING → CONFIRMED

#### Scenario: Transient failure with retry
- **WHEN** the submit daemon picks up a PENDING record and the backend fails transiently with retry_count below MAX_RETRIES
- **THEN** the record SHALL transition PENDING → SUBMITTING → FAILED_RETRYABLE, then FAILED_RETRYABLE → PENDING on next daemon cycle

#### Scenario: Retry threshold exceeded
- **WHEN** a FAILED_RETRYABLE record's retry_count reaches MAX_RETRIES
- **THEN** the record SHALL transition to FAILED_TERMINAL

#### Scenario: Terminal states are final
- **WHEN** a record reaches CONFIRMED or FAILED_TERMINAL
- **THEN** no further state transitions SHALL occur on that record

### Requirement: OPEN state reserved
The `OPEN` state SHALL be defined in the enum but SHALL NOT be used by any current code path. Records inserted by `/commit` SHALL use `PENDING` as the initial state.

#### Scenario: /commit inserts as PENDING
- **WHEN** TruCon receives a POST /commit request
- **THEN** the inserted record SHALL have status `PENDING`, not `OPEN`

### Requirement: Database queries use new state names
The `get_pending_by_chain` function SHALL query for records with status `PENDING`. The `get_failed_by_chain` function SHALL query for records with status `FAILED_RETRYABLE` OR `FAILED_TERMINAL`. The `get_queue_stats` function SHALL report counts for `PENDING`, `SUBMITTING`, `FAILED_RETRYABLE`, and `FAILED_TERMINAL` separately.

#### Scenario: Pending query returns only PENDING records
- **WHEN** `get_pending_by_chain(chain_id)` is called
- **THEN** only records with status = `PENDING` SHALL be returned

#### Scenario: Failed query returns both failure types
- **WHEN** `get_failed_by_chain(chain_id)` is called
- **THEN** records with status `FAILED_RETRYABLE` or `FAILED_TERMINAL` SHALL be returned

### Requirement: Crash recovery resets SUBMITTING on startup
On TruCon startup, the crash recovery process SHALL reset any records in `SUBMITTING` state to `PENDING`.

#### Scenario: SUBMITTING records recovered after crash
- **WHEN** TruCon starts and finds records with status `SUBMITTING`
- **THEN** those records SHALL be updated to status `PENDING`

### Requirement: Chain verification uses CONFIRMED
The `/verify-chain` endpoint SHALL consider a record confirmed when its status equals `CONFIRMED` and `log_id` is not NULL.

#### Scenario: Verification checks CONFIRMED status
- **WHEN** `/verify-chain/{chain_id}` inspects a record
- **THEN** only records with status `CONFIRMED` and non-null `log_id` SHALL count as Rekor-confirmed

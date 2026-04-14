## ADDED Requirements

### Requirement: Background thread lifecycle
The submit daemon SHALL run as a `threading.Thread(daemon=True)` started during the Trust API's FastAPI lifespan. It SHALL terminate when the Trust API process exits.

#### Scenario: Daemon starts with Trust API
- **WHEN** the Trust API process starts and the lifespan context manager enters
- **THEN** the submit daemon thread SHALL be started

#### Scenario: Daemon stops with Trust API
- **WHEN** the Trust API process receives a shutdown signal
- **THEN** the submit daemon thread SHALL terminate (daemon thread, exits with process)

### Requirement: Ordered Rekor submission
The submit daemon SHALL submit records to Rekor in ascending `sequence_num` order. It SHALL NOT skip a `PENDING` record to submit a later one.

#### Scenario: Submit in sequence order
- **WHEN** the daemon finds multiple PENDING records with `rtmr_extended=TRUE`
- **THEN** it SHALL submit the record with the lowest `sequence_num` first

#### Scenario: Blocked by earlier pending record
- **WHEN** record with `sequence_num=5` is PENDING and `sequence_num=6` is also PENDING
- **THEN** the daemon SHALL NOT submit `sequence_num=6` until `sequence_num=5` is CONFIRMED or manually resolved

### Requirement: Retry with failure threshold
The submit daemon SHALL retry failed Rekor submissions up to 10 times. On each failure, `retry_count` SHALL be incremented. When `retry_count` exceeds 10, the record's status SHALL be set to `FAILED`.

#### Scenario: Transient Rekor failure with retry
- **WHEN** a Rekor submission fails and `retry_count` is less than 10
- **THEN** the daemon SHALL increment `retry_count`, keep status as `PENDING`, and retry on the next poll cycle

#### Scenario: Permanent failure after max retries
- **WHEN** a Rekor submission fails and `retry_count` reaches 10
- **THEN** the daemon SHALL set the record's status to `FAILED`

### Requirement: FAILED records block subsequent submissions
When a record is in `FAILED` status, the submit daemon SHALL NOT submit any record with a higher `sequence_num` in the same chain. New commits (RTMR extend + queue insert) SHALL continue unblocked.

#### Scenario: FAILED record blocks later submissions
- **WHEN** a record with `sequence_num=5` has `status=FAILED`
- **THEN** records with `sequence_num > 5` in the same `chain_id` SHALL NOT be submitted to Rekor

#### Scenario: New commits continue despite FAILED record
- **WHEN** a FAILED record exists in the queue
- **THEN** new `POST /commit` requests SHALL still succeed (RTMR extend and queue insert proceed normally)

### Requirement: Polling interval
The submit daemon SHALL poll the `commit_queue` table every 5 seconds for records with `status=PENDING` and `rtmr_extended=TRUE`.

#### Scenario: Daemon polls periodically
- **WHEN** the daemon is running and idle
- **THEN** it SHALL check for pending records every 5 seconds

### Requirement: Confirmed record update
On successful Rekor submission, the daemon SHALL update the record's `status` to `CONFIRMED`, set `confirmed_at` to the current UTC timestamp, and store the Rekor `log_id` in the record's `log_id` field. It SHALL also update `chain_state.head_log_id`.

#### Scenario: Successful Rekor submission
- **WHEN** the Rekor API accepts a bundle submission and returns a log entry ID
- **THEN** the daemon SHALL update `status=CONFIRMED`, set `confirmed_at`, store `log_id`, and update `chain_state.head_log_id`

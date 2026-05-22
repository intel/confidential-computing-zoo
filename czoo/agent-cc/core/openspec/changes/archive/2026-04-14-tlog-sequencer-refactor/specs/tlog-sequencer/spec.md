## ADDED Requirements

### Requirement: Single-instance process enforcement
The Trust API process SHALL acquire an exclusive file lock on `/dev/shm/tc_api_queue/trust-api.lock` at startup using `fcntl.flock(LOCK_EX | LOCK_NB)`. If the lock is already held, the process SHALL exit immediately with a non-zero exit code and a descriptive error message.

#### Scenario: First instance starts successfully
- **WHEN** no other Trust API process holds the file lock
- **THEN** the process acquires the lock and starts normally

#### Scenario: Second instance rejected
- **WHEN** a Trust API process is already running and holds the file lock
- **THEN** the second process SHALL exit with a non-zero code and log "Another Trust API instance is already running"

### Requirement: Serialized commit sequencing
The Trust API SHALL serialize all commit operations behind a single `threading.Lock()`. Within the lock, it SHALL perform the following steps in order: (1) read current chain state, (2) RTMR extend with the event digest, (3) INSERT into commit_queue with `rtmr_extended=TRUE`, (4) UPDATE chain_state with new head.

#### Scenario: Concurrent commit requests serialize correctly
- **WHEN** two commit requests arrive simultaneously from different tc_api workers
- **THEN** the Trust API SHALL process them sequentially, each receiving a unique monotonically increasing `sequence_num`

#### Scenario: RTMR extend failure rolls back
- **WHEN** the RTMR sysfs write fails during a commit
- **THEN** the Trust API SHALL NOT insert the record into commit_queue and SHALL return an error to the caller

### Requirement: Chain state persistence
The Trust API SHALL maintain a `chain_state` table with one row per `chain_id`, tracking the current `head_record_id`, `head_log_id`, `sequence_num`, and `mr_value`.

#### Scenario: Chain state updated on commit
- **WHEN** a commit completes successfully (lock released)
- **THEN** the `chain_state` row for the given `chain_id` SHALL reflect the new `head_record_id`, incremented `sequence_num`, and updated `mr_value`

#### Scenario: Chain state survives process restart
- **WHEN** the Trust API process restarts after a clean shutdown
- **THEN** the `chain_state` table SHALL contain the state from the last successful commit

### Requirement: Crash recovery on startup
On startup, the Trust API SHALL scan `commit_queue` for records requiring recovery. Records with `rtmr_extended=TRUE` and `status=PENDING` SHALL be retained for Rekor submission. Records with `rtmr_extended=FALSE` SHALL be deleted. The `chain_state` SHALL be rebuilt from the highest `sequence_num` record with `rtmr_extended=TRUE`.

#### Scenario: Recover after crash with pending RTMR-extended records
- **WHEN** the Trust API restarts and finds records with `rtmr_extended=TRUE` and `status=PENDING`
- **THEN** those records SHALL remain in the queue for the submit daemon to process

#### Scenario: Discard records not yet RTMR-extended
- **WHEN** the Trust API restarts and finds records with `rtmr_extended=FALSE`
- **THEN** those records SHALL be deleted from `commit_queue`

### Requirement: Single-worker deployment
The Trust API SHALL be started with `--workers 1`. The `threading.Lock()` serialization guarantee is only valid within a single OS process.

#### Scenario: Trust API runs with one worker
- **WHEN** the Trust API is started via uvicorn
- **THEN** it SHALL be configured with `--workers 1`

## RENAMED Requirements

### Requirement: Single-instance process enforcement
FROM: The Trust API process SHALL acquire an exclusive file lock on `/dev/shm/tc_api_queue/trust-api.lock`
TO: The TruCon process SHALL acquire an exclusive file lock on `/dev/shm/tc_api_queue/trucon.lock`

### Requirement: Serialized commit sequencing
FROM: The Trust API SHALL serialize all commit operations behind a single `threading.Lock()`.
TO: TruCon SHALL serialize all commit operations behind a single `threading.Lock()`.

### Requirement: Chain state persistence
FROM: The Trust API SHALL maintain a `chain_state` table
TO: TruCon SHALL maintain a `chain_state` table

### Requirement: Crash recovery on startup
FROM: On startup, the Trust API SHALL scan `commit_queue` for records requiring recovery.
TO: On startup, TruCon SHALL scan `commit_queue` for records requiring recovery.

### Requirement: Single-worker deployment
FROM: The Trust API SHALL be started with `--workers 1`.
TO: TruCon SHALL be started with `--workers 1`.

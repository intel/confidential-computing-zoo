## ADDED Requirements

### Requirement: Memory-Backed Storage Pre-requisite
The system SHALL ensure the queue database is instantiated on a memory-backed file system (`/dev/shm`) and SHALL explicitly create a dedicated directory structure (e.g. `/dev/shm/tc_api_queue`) with exclusive ownership `0700` before initializing the SQLite connection.

#### Scenario: Daemon starts successfully
- **WHEN** the `tlog_daemon` or the `API` service initializes the SQLite queue
- **THEN** it creates `/dev/shm/tc_api_queue` and assigns `0700` permissions restricting all access to the active user

### Requirement: Swapping Deployment Contract
The system SHALL surface the necessity of memory pinning or disabling swap (e.g., `memory-swappiness=0`) so that uncommitted events are never synced to secondary untrusted storage by the kernel.

#### Scenario: Running deployment checks
- **WHEN** executing deployment scripts or environment validations
- **THEN** warnings or hard checks validate that swap is disabled or memory pinning is active

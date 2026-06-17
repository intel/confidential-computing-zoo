## ADDED Requirements

### Requirement: Independent process execution
The submission daemon MUST function as a standalone, runnable python script (`tlog_daemon.py`).

#### Scenario: Running the daemon independently
- **WHEN** executing `python tlog_daemon.py`
- **THEN** the process initializes its own `TrustedLogAPI` instance and continuously polls the commit queue.

### Requirement: Independent queue observation and task execution
The isolated daemon process MUST be capable of processing the local DB via `get_commit_queue_status` and triggering `submit_record` using identically configured local adapters.

#### Scenario: Consuming queued entries
- **WHEN** there exist pending items within `/dev/shm/commit_queue.db` 
- **THEN** the daemon detects those items and successfully submits them to the configured immutable log backend.
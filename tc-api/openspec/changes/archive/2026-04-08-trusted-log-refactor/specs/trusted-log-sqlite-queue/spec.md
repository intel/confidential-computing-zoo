## ADDED Requirements

### Requirement: SQLite Commit Queue Persistence
The system SHALL persist committed `EventLog` records to a local SQLite database prior to completing the `commit_record` API execution and before extending the hardware measurement register.

#### Scenario: Successful commit sequence
- **WHEN** a client calls `commit_record()`
- **THEN** the system generates the cryptographically bound `EventLog`
- **AND** the system safely records it into the SQLite table using Write-Ahead-Log (WAL) mode
- **AND** only then executes the hardware MR extension

### Requirement: Commit Queue Retry State
The system MUST retain submission status (PENDING, CONFIRMED) and retry counters per record within SQLite.

#### Scenario: Backend unavailable
- **WHEN** the Submission Daemon fails to push an EventLog to the Rekor API
- **THEN** the system marks the record's retry count and updates its timestamp inside SQLite without deleting the payload

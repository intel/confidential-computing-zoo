## ADDED Requirements

### Requirement: Ephemeral Storage Location
The system SHALL establish all local commit queue SQLite database files on an ephemeral, non-persistent, memory-backed storage path (e.g. `/dev/shm` on Linux).

#### Scenario: Database initialization
- **WHEN** the `init_db()` phase runs at application startup
- **THEN** the system points the connection to a `tmpfs` volume by default, ensuring the resulting `.db` artifact is encrypted in RAM and not synchronized to the underlying host disk.
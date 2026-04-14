## ADDED Requirements

### Requirement: Daemon Spawning in FastAPI
The system SHALL deploy a multi-threaded daemon directly inside the FastAPI Web process for asynchronously draining the Commit Queue.

#### Scenario: Application Startup
- **WHEN** the FastAPI application enters the `lifespan` hook
- **THEN** the Submission Daemon thread is started
- **AND** it safely polls the SQLite commit queue periodically

### Requirement: Stateless DSSE Upload
The daemon MUST process background submission without invoking any dynamic OIDC tokens, relying purely on the static pre-signed payloads stored in the queue.

#### Scenario: Upload Retry
- **WHEN** the Submission Daemon pulls a previously failed payload
- **THEN** it executes `submit_record()`
- **AND** uploads the pre-signed In-Toto DSSE envelope via the Rekor API client directly

### Requirement: Graceful Shutdown
The daemon MUST gracefully shut down to avoid corruption of the SQLite database.

#### Scenario: Process Restart
- **WHEN** the FastAPI process receives a SIGKILL/SIGTERM
- **THEN** the `lifespan` hook signals the Thread to safely complete its current push and disconnect from the SQLite file

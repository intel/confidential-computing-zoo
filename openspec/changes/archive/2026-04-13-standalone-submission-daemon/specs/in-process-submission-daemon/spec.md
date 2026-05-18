## REMOVED Requirements

### Requirement: start_submission_daemon embedded within API
**Reason**: Embedded Daemon processing duplicates execution threads across multiple Uvicorn API workers, promoting race-condition collisions within transient databases like SQLite.
**Migration**: Execution has been refactored over to an out-of-process architecture.

### Requirement: stop_submission_daemon embedded within API
**Reason**: Out-of-process isolation nullifies the internal teardown routines in API cleanup hooks.
**Migration**: Execution mapping matches system process termination vectors for the Daemon process.
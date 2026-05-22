## MODIFIED Requirements

### Requirement: Crash recovery on startup
On startup, TruCon SHALL scan `commit_queue` for records requiring recovery. Records with `rtmr_extended = FALSE` or NULL SHALL be deleted (incomplete commits). Records with status `SUBMITTING` SHALL be reset to `PENDING` (interrupted submission). Recovery SHALL complete before the submit daemon begins processing.

#### Scenario: SUBMITTING records reset on startup
- **WHEN** TruCon starts and the `commit_queue` contains records with status `SUBMITTING`
- **THEN** those records SHALL be updated to status `PENDING` before the submit daemon starts

#### Scenario: Incomplete commits deleted on startup
- **WHEN** TruCon starts and the `commit_queue` contains records with `rtmr_extended = FALSE` or NULL
- **THEN** those records SHALL be deleted from the queue

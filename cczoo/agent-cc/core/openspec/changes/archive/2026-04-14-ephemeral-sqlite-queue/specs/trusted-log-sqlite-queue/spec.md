## ADDED Requirements

### Requirement: Lossy Crash Recovery
The queue SHALL unconditionally reset upon VM reboots (implied by `dev/shm` reset), inherently enforcing identical lifespans for uncommitted queued signatures and their respective ephemeral hardware quotes.

#### Scenario: Submitting event post-crash
- **WHEN** the VM completely restarts and initiates the hardware TD bounds anew
- **THEN** previous uncommitted local events vanish cryptographically, retaining 100% cryptographic validity logic on subsequent commits

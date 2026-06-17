## Why

In a Confidential Computing threat model (like TDX or SEV), the host hypervisor is strictly assumed to be untrusted. While the TD VM's memory maintains data-in-use protection, persisting our SQLite `CommitQueue` containing plaintext `EventLog` payloads to the local virtual disk completely nullifies this protection. Storing data at rest unencrypted leaves us vulnerable to host-initiated tampering, rollback attacks, and sensitive data leakage (e.g., leaked container builds or keys). To balance swift and reliable processing without developing complex key-broker encryption, we must keep this data purely in memory.

## What Changes

- Switch the SQLite database path for the `CommitQueue` to an ephemeral in-memory proxy structure, specifically leveraging a RAM disk like `tmpfs` (e.g. `/dev/shm`).
- We accept the trade-off that a sudden OOM killer or host-initiated reset will cause us to lose un-synced queue requests (logs not fully committed remotely).
- Update the default DB configuration initialization paths to rely on this in-memory filesystem implicitly over standard block storage.
- **BREAKING**: Local untrusted disk will no longer passively store recovery logs across total TD VM cold reboots.

## Capabilities

### New Capabilities
- `ephemeral-commit-queue`: The `database.py` configurations will handle writing to `tmpfs` RAM disk paths for its SQLite file, ensuring the database stays inside encrypted TCB memory space.

### Modified Capabilities


## Impact

- `config.py` and `database.py`: Will undergo changes to update and default the `tmpfs` disk location.
- Deployment environment: May dictate configuration checks confirming `tmpfs` capacity so the SQLite database size doesn't overrun memory.
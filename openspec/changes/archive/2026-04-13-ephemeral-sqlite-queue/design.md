## Context

The `TrustedLogAPI` establishes local queue logic acting as an intermediary write-ahead layer before events are published to transparent logs. In Linux TDX/SEV Confidential Computing settings, the hypervisor (Host) is part of the threat space but is still the entity mediating actual storage drivers (`/dev/sda` etc.). If the SQLite database rests on regular untrusted disk, its contents implicitly violate confidentiality and integrity. The TD VM natively encrypts generic RAM mapped inside the virtual machine boundary.

## Goals / Non-Goals

**Goals:**
- Shift the SQLite deployment directory into an in-memory mapped `/dev/shm` (shared memory) directory by default or configuration.
- Exploit TD VM Data-In-Use protections as a zero-cost Data-At-Rest protection model.

**Non-Goals:**
- Introducing custom heavy AES-GCM or App-level database encryption layers which involve KMS and key retrieval flows.
- Ensuring zero log loss on total VM shutdown or crash (the local queue is designed around temporary retries, not permanent lifecycle archiving prior to submission).

## Decisions

- **SQLite Database Path Update**: Using `/dev/shm/commit_queue.db` as the new default target. `/dev/shm` acts as a POSIX standard memory-backed `tmpfs`.
- **Database Configuration Changes**: Change the config constants so the application creates directories within `/dev/shm` if they do not exist implicitly.

## Risks / Trade-offs

- **Risk: OOM (Out-of-Memory)**
  - The SQLite database expanding limitlessly without disk paging could cause memory pressure leading to pod/process kills if the daemon fails to drain reliably.
  - *Mitigation*: We rely on the log size being relatively small and the Daemon maintaining high drain throughput, ensuring the queue length averages near zero.
- **Risk: Crash Data Loss**
  - Ephemeral paths destroy unsynced data immediately exactly upon a reboot event.
  - *Mitigation*: This aligns with "Data security rules absolute availability", acknowledging that failing-closed is better than leaking state in high-security bounds.
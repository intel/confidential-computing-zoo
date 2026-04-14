## Context

The system currently places the internal SQLite event queue on traditional filesystem paths, which persist across VM reboots. In an Intel TDX environment, a VM crash/reboot resets the hardware TDX Measurement Registers (RTMRs). Persistent queue state will subsequently lack matching cryptographically bound hardware quotes for the local machine's identity, causing verification to fail. A volatile queue perfectly aligns the software event lifecycle to corresponding TDX VM hardware lifecycles.

## Goals / Non-Goals

**Goals:**
- Transition the `queue.db` file to `/dev/shm` (a `tmpfs`-based RAM file system) to achieve strict Lifecycle Alignment between the event queue and the underlying hardware TDX memory encryption context.
- Implement Discretionary Access Control (DAC) isolation to prevent other processes in the same Guest OS from casually reading sensitive payloads from SQLite WAL/SHM temporary files.
- Enforce basic environment checks or contracts indicating memory should not be swapped.

**Non-Goals:**
- Implementing custom memory-locking APIs (like `mlockall` via `ctypes` in Python) which is fragile and often requires elevated capabilities. Swapping defenses will be relegated to the deployment layer.

## Decisions

- **Storage Location**: We will create a robust initialization flow in `trusted_container_log/database.py` that defaults the SQLite path to `/dev/shm/tc_api_queue/queue.db`.
- **DAC Isolation Boundary**: The python initialization routine will ensure the `/dev/shm/tc_api_queue` directory exists and has strictly `0700` permissions. This guarantees that only the process owner (the `tlog_daemon` and `API` host) can access `queue.db`, `queue.db-wal`, and `queue.db-shm`.
- **Handling Process Crashes without VM Reboots**: Since `/dev/shm` persists across application crashes but clears on OS reboots, this is acceptable. If `api` or `tlog_daemon` crash but the VM stays up, the SQLite state is immediately recoverable, and the RTMR logs are still valid in hardware.

## Risks / Trade-offs

- **Risk**: Out of Memory (OOM) swapping to unencrypted disks exposing `/dev/shm` secrets.
  - **Mitigation**: Add warning logic in `start.sh` or deployment manifests (`docker-compose.yml`, K8s resources) to ensure `memory-swappiness=0` or `medium: "Memory"`.
- **Risk**: Discarded uncommitted events after VM crash.
  - **Mitigation**: Accepted as a fundamental feature, not a bug. If the machine goes down, the TD hardware unseals its state, rendering previously uncommitted signatures invalid. Data loss here is mathematically intended.

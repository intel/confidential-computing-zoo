## Why

In a Confidential Computing (e.g., Intel TDX) environment, local event queues shouldn't outlive the Trust Domain (TD) that created them. If a VM crashes, hardware Measurement Registers (RTMRs) are reset, making any persistent but uncommitted queue events cryptographically invalid (missing quotes). Moving our SQLite queue to an ephemeral, memory-backed volume (`/dev/shm`) intrinsically aligns the lifecycle of the queue with the hardware TEE (Lifecycle Alignment), resolving this consistency paradox while simultaneously boosting I/O performance.

## What Changes

- Migrate the local SQLite database used for the event queue from standard disk paths to `/dev/shm/tc_api_queue/`.
- Introduce strict Discretionary Access Control (DAC) isolation (e.g., `0700` permissions) on the `/dev/shm` directory to prevent intra-TD data leakage from the SQLite WAL/SHM files to other unprivileged processes.
- Establish an anti-swapping deployment contract (e.g., disabling swap or setting Swappiness to 0) to ensure the memory-backed queue is never swapped to an unencrypted host disk, which would violate the TDX memory encryption boundary.

## Capabilities

### New Capabilities
- `ephemeral-queue-storage`: Define the behavior, security boundary, and volatile nature of the memory-backed queue storage.

### Modified Capabilities
- `trusted-log-sqlite-queue`: Modify existing queue assumptions to mandate ephemeral lifecycle alignment and specific permission boundaries.

## Impact

- `trusted_container_log/database.py`: Paths and directory initialization logic will need updates to enforce `0700` permissions and target `/dev/shm`.
- Deployment Configuration (`start.sh`, `docker-compose.yml`, K8s): Must enforce swap restrictions or provide memory-medium emptyDirs.

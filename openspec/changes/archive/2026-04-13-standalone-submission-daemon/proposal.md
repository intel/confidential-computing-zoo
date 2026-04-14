## Why

Currently, the `TrustedLogAPI` hosts a `start_submission_daemon` method which launches a `threading.Thread` within the API process itself. In a production environment with multiple API workers (e.g., Uvicorn starting multiple workers), this leads to multiple daemon threads being launched concurrently. Because the underlying SQLite WAL queue lacks `SELECT ... FOR UPDATE` row-level locks, these multiple threads can simultaneously fetch the same `next_record_id`, leading to race conditions and duplicate submissions to the overarching Sigstore/Remote Backend.

Extracting the daemon into a standalone independent process completely resolves this issue by ensuring a singleton consumer model. Furthermore, this isolates crashes (backend network timeouts will never kill the API processing) and strictly adheres to the principle of least privilege in Confidential Computing—the API solely communicates with the local TDX hardware limits, while the daemon solely requires external network access to Sigstore.

## What Changes

- Extract the submission daemon logic currently in `TrustedLogAPI` into a standalone, independently executable script (`tlog_daemon.py`).
- **BREAKING**: Remove daemon lifecycle methods (`start_submission_daemon` and `stop_submission_daemon`) and the internal `_daemon_thread` tracking from `TrustedLogAPI`.
- Provide configurations or startup scripts (e.g., `docker-compose.yml` modifications) to instantiate this separate daemon service alongside the main API workload.

## Capabilities

### New Capabilities
- `out-of-process-submission-daemon`: Capability to run the signature submission daemon separately from the primary API boundary, consuming tasks decoupled via the ephemeral `/dev/shm` SQLite pool.

### Modified Capabilities
- `in-process-submission-daemon`: The existing capability of tracking and managing background submission worker threads will be removed or sunsetted in favor of the out-of-process component.

## Impact

- **Code impacted**: `trusted_container_log/api.py` (removing thread lifecycle code) and addition of a new `tlog_daemon.py` root execution script.
- **Infrastructure impacted**: Deployment artifacts like `docker-compose.yml` or `start.sh` will need an additional service entry to launch the background daemon independently.
- **Security Impact**: Improved. API workers can have their egress networking strictly limited, while the daemon holds restricted host access.
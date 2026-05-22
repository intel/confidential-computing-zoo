## Context

The `TrustedLogAPI` is responsible for committing container execution events to an immutable log (Sigstore) and extending those events into local CC measurements (TDX RTMR). Part of this lifecycle involves asynchronous confirmation: a background daemon picks up queued events and pushes them over the network. 

Presently, this daemon is spawned as an in-process thread (`_daemon_thread`) internally mounted onto the `TrustedLogAPI` class. In Uvicorn/FastAPI deployments involving multiple worker processes, multiple such threads are inadvertently launched. Not only does this break the "singleton" assumption of the loop, but it additionally suffers from race conditions where multiple workers concurrently try to drain the exact same records from an ephemeral SQLite-backed commit queue situated at `/dev/shm/commit_queue.db`. Removing this internal daemon functionality prevents duplication conflicts out-of-the-box.

## Goals / Non-Goals

**Goals:**
- Eliminate race conditions by removing `start_submission_daemon`, `stop_submission_daemon` logic from `TrustedLogAPI`.
- Create a distinct executable script (`tlog_daemon.py`) responsible for consuming the same `/dev/shm/commit_queue.db` queue.
- Maintain existing test coverage while updating relevant mocking/simulating tests as appropriate.
- Refactor the Docker Compose files and startup scripts to initialize the singleton Daemon separate from Uvicorn.

**Non-Goals:**
- Completely rewriting the Retry algorithms or Exponential Backoff strategies—migrating the execution *context* is enough.
- Introducing heavier external queueing brokers (e.g., Redis, RabbitMQ); SQLite running within `tmpfs` is explicitly retained to satisfy Confidential Computing RAM isolation properties.

## Decisions

1. **Daemon Loop Implementation**:
   - Create `tlog_daemon.py` at the root alongside `main.py`.
   - The standalone file will instantiate a `TrustedLogAPI` (to gain access to the injected adapters) and continuously invoke `get_commit_queue_status()` and `submit_record()`, mimicking the body of the previous embedded daemon loop.

2. **API Lifecycle Refactoring**:
   - Strip instances of `threading.Event`, `threading.Thread` and the associated lifecycle functions (`start_submission_daemon`, `stop_submission_daemon`) from `trusted_container_log/api.py`.
   - Within `main.py` explicitly stop calling `trusted_log.start_submission_daemon()`. 

3. **Multi-process Orchestration**:
   - `start.sh` and `docker-compose.yml` will be amended to launch `python tlog_daemon.py &` or provide it as a separate container service targeting the identical `/dev/shm` mount point. For testing scripts like `run_tests.sh`, we might choose to mock or run the daemon momentarily.

## Risks / Trade-offs

- **[Risk] Operational Complexity**: A two-process system requires robust orchestrator management (systemd, compose) over a single monolithic Python app. 
  - *Mitigation*: Proper startup scripts and docker configurations are updated accordingly.
- **[Risk] Testing Regressions**: A number of unit tests presently might synchronously boot the threading daemon to check if items vanish from the queue. Breaking this thread away will cause these tests to hang.
  - *Mitigation*: Adjust unit tests to either mock daemon executions or run the daemon loop manually within test boundaries instead of relying on the automatic thread.
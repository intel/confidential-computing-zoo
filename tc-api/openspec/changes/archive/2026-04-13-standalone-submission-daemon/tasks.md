## 1. Remove In-Process Daemon Lifecycle

- [x] 1.1 In `trusted_container_log/api.py`, delete the `start_submission_daemon()` method from the `TrustedLogAPI` class.
- [x] 1.2 In `trusted_container_log/api.py`, delete the `stop_submission_daemon()` method from the `TrustedLogAPI` class.
- [x] 1.3 In `trusted_container_log/api.py`, remove `self._stop_event` and `self._daemon_thread` from the `TrustedLogAPI.__init__` initialization.
- [x] 1.4 In `main.py`, remove the `trusted_log.start_submission_daemon()` and `trusted_log.stop_submission_daemon()` invocations from the `lifespan` manager context.

## 2. Create the Standalone Executable Daemon

- [x] 2.1 Create a new root-level file named `tlog_daemon.py`.
- [x] 2.2 In `tlog_daemon.py`, import the necessary dependencies: `logging`, `time`, configuration values, `TrustedLogAPI`, and inject the `SigstoreLogAdapter`. (Note: TDX extension hardware is NOT needed here).
- [x] 2.3 In `tlog_daemon.py`, instantiate `TrustedLogAPI` purely configuring the `immutable_log` parameter with the `SigstoreLogAdapter`.
- [x] 2.4 In `tlog_daemon.py`, write the `while True:` loop calling `get_commit_queue_status()` and `submit_record` with exponential backoff delay loops. Implement standard interrupt (SIGTERM/SIGINT) handling to gracefully exit the script.

## 3. Update Infrastructure Orchestration

- [x] 3.1 Update `start.sh` so that it runs `python tlog_daemon.py &` before starting Uvicorn, and saves the PID to ensure cleanup.
- [x] 3.2 Update `docker-compose.yml` to define a separate `tlog-daemon` service that mimics the environment context of the tc-api service but targets `python tlog_daemon.py` directly as its command.

## 4. Test Remediation

- [x] 4.1 In `test_tlog_impl.py` or `test_tlog_refactored.py`, remove any mocked invocations of `start_submission_daemon` or adapt `time.sleep` assumptions if they previously relied on the thread fetching records.
- [x] 4.2 Verify and adjust focused unit coverage for daemon-thread mechanics rather than relying on a catch-all legacy test module.
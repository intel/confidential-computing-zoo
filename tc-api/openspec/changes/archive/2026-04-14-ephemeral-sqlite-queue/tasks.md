## 1. Storage & DAC Isolation Updates

- [x] 1.1 In `trusted_container_log/database.py`, update `init_db` (or create a new helper) to override or default the SQLite path to `/dev/shm/tc_api_queue/queue.db`.
- [x] 1.2 In `trusted_container_log/database.py`, add logic to ensure the directory `/dev/shm/tc_api_queue` exists and apply `os.chmod` to yield `0700` permissions exclusively for the process owner.

## 2. Deployment Swapping Constraints

- [x] 2.1 In `docker-compose.yml`, update the API and Daemon services to mount `/dev/shm` appropriately if needed or add constraints to prevent memory swapping to disk via `mem_swappiness: 0`.
- [x] 2.2 Add a deployment check or note in `start.sh` warning if `swap` is active and potentially terminating initialization entirely in strict environments.

## 3. Test Alignment

- [x] 3.1 Update `test_tlog_refactored.py` tests that instantiate database files to mock or accommodate the new lifecycle assumptions and directory pathings.
- [x] 4.1 Update trusted-log/architecture.md to reflect the new ephemeral memory-backed SQLite queue and lifecycle alignment.

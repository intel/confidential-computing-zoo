## 1. Environment and Configuration Refactor

- [x] 1.1 Update `config.py` (if it exists and exports the DB path) or `trusted_container_log/database.py` to use `/dev/shm/commit_queue.db` as the default SQLite database path.
- [x] 1.2 Verify that the application successfully initializes the SQLite database upon startup against this new ephemeral target.

## 2. Test Validation

- [x] 2.1 Identify and adjust any tests that assumed the commit queue database would reside in the local directory (e.g. `./commit_queue.db`). Ensure mock paths still use standard `tmp_path` fixtures to avoid cluttering `shm` during testing.
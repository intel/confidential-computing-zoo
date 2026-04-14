## 1. Code Rename: Trust API → TruCon

- [x] 1.1 Rename `trust_api.py` to `trucon.py` and update all internal references (FastAPI app title, log messages, comments)
- [x] 1.2 Rename file lock path from `trust-api.lock` to `trucon.lock` in `trucon.py`
- [x] 1.3 Update `config.py`: rename `TRUST_API_URL` to `TRUCON_URL`
- [x] 1.4 Update `main.py`: change import and reference from `trust_api_url` / `TRUST_API_URL` to `trucon_url` / `TRUCON_URL`
- [x] 1.5 Update `trusted_container_log/api.py`: rename `trust_api_url` parameter to `trucon_url`, update `_post_to_trust_api` method name to `_post_to_trucon`
- [x] 1.6 Update `docker-compose.yml`: rename `trust-api` service to `trucon`, update command to `trucon:app`, update env var `TRUST_API_URL` to `TRUCON_URL`
- [x] 1.7 Update `start.sh`: rename uvicorn target from `trust_api:app` to `trucon:app`, update `TRUST_API_URL` export to `TRUCON_URL`
- [x] 1.8 Update `test_sequencer_refactor.py`: rename all references from `trust_api` to `trucon`
- [x] 1.9 Update `test_tlog_refactored.py`: rename any references from `trust_api_url` to `trucon_url`
- [x] 1.10 Run all tests (`pytest test_unit.py test_sequencer_refactor.py test_tlog_refactored.py -v`) and verify they pass

## 2. Top-Level Architecture Document

- [x] 2.1 Update top-level `architecture.md` Section 3 (High-Level Topology) to reflect implemented TruCon architecture (sequencer lock, embedded daemon, SQLite queue) while keeping the 3-service diagram
- [x] 2.2 Update Section 4.3 (TruCon Core Service) to describe currently implemented capabilities vs planned capabilities
- [x] 2.3 Update Section 4.4 (Submission Worker) to describe the embedded daemon model (threading.Thread)
- [x] 2.4 Mark Section 4.2 (Docktap Service) with "Status: Planned — not yet implemented"
- [x] 2.5 Update Section 5.2 (Mapping Model) with "Status: Planned — not yet implemented"
- [x] 2.6 Add cross-reference to `trusted-log/architecture.md` for TruCon internal implementation details
- [x] 2.7 Remove TruCon internal details (threading.Lock, SQLite schema columns, crash recovery flags) that belong only in `trusted-log/architecture.md`

## 3. Trusted-Log Architecture Document

- [x] 3.1 Replace all "Trust API" references with "TruCon" in `trusted-log/architecture.md`
- [x] 3.2 Replace all "Trust API" references with "TruCon" in `trusted-log/api.md`
- [x] 3.3 Replace all "Trust API" references with "TruCon" in `trusted-log/README.md`
- [x] 3.4 Remove any references to top-level `architecture.md` from `trusted-log/` documents (ensure one-way dependency)
- [x] 3.5 Add section in `trusted-log/architecture.md` documenting prev_log_id chaining as a future secondary ordering method for non-TEE environments

## 4. Validation

- [x] 4.1 Verify `trucon.py` starts successfully with `uvicorn trucon:app --workers 1`
- [x] 4.2 Verify `start.sh` runs without errors
- [x] 4.3 Verify `docker-compose.yml` is valid (`docker compose config`)
- [x] 4.4 Grep for any remaining "trust.api" or "TRUST_API" references in code and config files (should find zero)
- [x] 4.5 Verify `trusted-log/` docs contain no references to top-level `architecture.md`

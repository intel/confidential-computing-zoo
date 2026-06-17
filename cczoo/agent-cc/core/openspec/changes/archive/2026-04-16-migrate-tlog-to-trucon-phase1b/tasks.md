## 1. Delete legacy code

- [x] 1.1 Delete `src/tc_api/trusted_container_log/tlog_chain.py`
- [x] 1.2 Update `src/tc_api/trusted_container_log/__init__.py` to export `TrustedLogAPI` instead of `ChainedTransparencyLog`
- [x] 1.3 Remove `verify_tlog()` method from `src/tc_api/services.py` (including the local `from .trusted_container_log import ChainedTransparencyLog` import)
- [x] 1.4 Remove `/api/verify-tlog` endpoint from `src/tc_api/main.py`
- [x] 1.5 Remove any remaining references to `ChainedTransparencyLog` or `tlog_chain` in docs (`docs/trusted-log/`)

## 2. Persist event_digest in TruCon

- [x] 2.1 Add `event_digest TEXT` column to `commit_queue` table creation in `trucon.py` (ALTER TABLE for existing DBs)
- [x] 2.2 Update `insert_record()` to accept and store `event_digest`
- [x] 2.3 Update `/commit` endpoint to pass `req.event_digest` through to `insert_record()`

## 3. Implement GET /verify-chain/{chain_id}

- [x] 3.1 Add Pydantic response models for `ChainVerificationResponse` and `ChainEntryResult` in `trucon.py`
- [x] 3.2 Implement the verification function: query all `commit_queue` records for `chain_id` ordered by `sequence_num`, check sequence continuity, RTMR chain integrity (using `event_digest`), and Rekor confirmation status
- [x] 3.3 Handle edge cases: non-existent chain (404), NULL `event_digest` (skip RTMR check), NULL `mr_value` (set `rtmr_available: false`), mixed NULL/non-NULL
- [x] 3.4 Register `GET /verify-chain/{chain_id}` endpoint on the TruCon FastAPI app

## 4. Validation

- [x] 4.1 Verify no remaining references to `ChainedTransparencyLog` or `tlog_chain` in `src/` (except archived openspec)
- [x] 4.2 Verify both `main.py` and `services.py` pass `py_compile`
- [x] 4.3 Verify `trucon.py` passes `py_compile` and the TruCon app loads with the new endpoint
- [x] 4.4 Run `pytest tests/test_tdx_mr_adapter.py -v` and fix any import breakage

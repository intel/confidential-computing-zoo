## 1. Enum & Type Changes

- [x] 1.1 Extend `SubmitStatus` enum in `tlog/types.py` to 6 values: `OPEN`, `PENDING`, `SUBMITTING`, `CONFIRMED`, `FAILED_RETRYABLE`, `FAILED_TERMINAL` (lowercase string values)

## 2. Database Layer

- [x] 2.1 Update `get_pending_records()` — query `WHERE status = 'PENDING'` (unchanged, confirm)
- [x] 2.2 Update `get_pending_by_chain()` — query `WHERE status = 'PENDING'` (unchanged, confirm)
- [x] 2.3 Update `get_failed_by_chain()` — query `WHERE status IN ('FAILED_RETRYABLE', 'FAILED_TERMINAL')`
- [x] 2.4 Update `update_record_confirmed()` — SET `status = 'CONFIRMED'` (unchanged, confirm)
- [x] 2.5 Update `get_queue_stats()` — report `PENDING`, `SUBMITTING`, `FAILED_RETRYABLE`, `FAILED_TERMINAL` counts separately
- [x] 2.6 Add `reset_submitting_to_pending()` function for crash recovery
- [x] 2.7 Add `set_status_submitting()` helper for daemon to mark SUBMITTING before backend call

## 3. Submit Daemon

- [x] 3.1 In `_submit_daemon_tick()`: mark record SUBMITTING before backend call (`set_status_submitting`)
- [x] 3.2 On success: transition SUBMITTING → CONFIRMED (existing `update_record_confirmed`)
- [x] 3.3 On failure: transition SUBMITTING → FAILED_RETRYABLE with `increment_retry`
- [x] 3.4 In `_handle_retry()`: check retry threshold — if exceeded, transition to FAILED_TERMINAL instead of staying FAILED_RETRYABLE
- [x] 3.5 Update `_submit_daemon_tick()` to also handle FAILED_RETRYABLE records: reset to PENDING for retry

## 4. Crash Recovery

- [x] 4.1 Add `reset_submitting_to_pending()` call in TruCon startup (lifespan), after existing recovery logic and before daemon starts

## 5. /commit Endpoint

- [x] 5.1 Confirm `/commit` still inserts with status `PENDING` (no change needed, verify)

## 6. /verify-chain

- [x] 6.1 Confirm `is_confirmed` check uses `status == 'CONFIRMED'` (no change needed, verify)

## 7. Tests — New

- [x] 7.1 Test: SubmitStatus enum has exactly 6 members with correct values
- [x] 7.2 Test: PENDING → SUBMITTING → CONFIRMED transition (happy path)
- [x] 7.3 Test: SUBMITTING → FAILED_RETRYABLE → PENDING retry cycle
- [x] 7.4 Test: FAILED_RETRYABLE → FAILED_TERMINAL after MAX_RETRIES
- [x] 7.5 Test: FAILED_TERMINAL blocks subsequent records in same chain
- [x] 7.6 Test: Crash recovery resets SUBMITTING → PENDING on startup
- [x] 7.7 Test: get_failed_by_chain returns both FAILED_RETRYABLE and FAILED_TERMINAL

## 8. Tests — Update Existing

- [x] 8.1 Update `test_sequencer_refactor.py` — replace all `"FAILED"` with `"FAILED_TERMINAL"` or `"FAILED_RETRYABLE"` as appropriate
- [x] 8.2 Update `test_idempotency.py` — replace `"FAILED"` status references
- [x] 8.3 Update `test_tlog_refactored.py` — no changes needed (only uses `"PENDING"`)
- [x] 8.4 Run full regression: 60/60 tests pass

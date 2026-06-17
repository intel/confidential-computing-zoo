## 1. Database Schema

- [x] 1.1 Add `created_at` column migration in `_migrate_legacy_schema()`: `ALTER TABLE commit_queue ADD COLUMN created_at TEXT`
- [x] 1.2 Add backfill in migration: `UPDATE commit_queue SET created_at = updated_at WHERE created_at IS NULL`
- [x] 1.3 Update `insert_record()` to set `created_at = datetime.utcnow().isoformat()` at INSERT time
- [x] 1.4 Add `total_retry_count` (SUM of retry_count) to `get_queue_stats()` return dict

## 2. Response Model Update

- [x] 2.1 Add `total_retry_count: int = 0` field to `CommitQueueStatusResponse` in `trucon/app.py`
- [x] 2.2 Update `GET /status` handler to pass `total_retry_count` from `get_queue_stats()`

## 3. Metric Emissions — /commit Handler

- [x] 3.1 Add `time.perf_counter()` at top of `/commit` handler (before lock) and compute `latency_ms` at return
- [x] 3.2 Emit `metric=commit_latency` log line on both normal and idempotent paths with `latency_ms`, `record_id`, `idempotent` fields
- [x] 3.3 Emit `metric=idempotency_hit` log line in the dedup branch with `key`, `chain_id`, `record_id`

## 4. Metric Emissions — Submit Daemon

- [x] 4.1 Add `time.perf_counter()` before `set_status_submitting()` and compute `latency_ms` at outcome
- [x] 4.2 Emit `metric=submit_latency` log line after each submission attempt with `latency_ms`, `record_id`, `outcome`
- [x] 4.3 Emit `metric=confirmation_lag` log line when confirming a record: compute `lag_ms = confirmed_at - created_at`; skip if `created_at` is NULL
- [x] 4.4 Emit `metric=queue_snapshot` log line at end of each daemon tick with `queue_depth`, `submitting_count`, `failed_retryable_count`, `failed_terminal_count`, `total_retry_count`

## 5. Tests — New

- [x] 5.1 Test: `created_at` column exists after migration and is populated on insert
- [x] 5.2 Test: `created_at` is NOT updated by `update_status()`
- [x] 5.3 Test: `get_queue_stats()` returns `total_retry_count` as SUM of retry_count
- [x] 5.4 Test: `/commit` handler emits `metric=commit_latency` log line (capture via `caplog`)
- [x] 5.5 Test: idempotent `/commit` emits both `metric=commit_latency` with `idempotent=true` and `metric=idempotency_hit`
- [x] 5.6 Test: `metric=queue_snapshot` log line contains all 5 count fields
- [x] 5.7 Test: `metric=confirmation_lag` is emitted with correct `lag_ms` on confirm

## 6. Tests — Update Existing

- [x] 6.1 Update `test_status_response.py` and `test_sequencer_refactor.py` to account for `total_retry_count` in stats
- [x] 6.2 Run full regression: `pytest tests/ -v`

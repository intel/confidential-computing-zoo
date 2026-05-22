## Why

The architecture requires 7 minimum observability metrics (§8.2) but TruCon has zero instrumentation. Operators cannot see queue depth, latency, failure rates, or retry behavior without manually querying SQLite. All prerequisites are now met: GAP-02 (idempotency dedup path), GAP-06 (granular lifecycle states), and FIX-02 (status endpoints) are complete, providing the data sources these metrics need.

## What Changes

- Add structured log emissions for all 7 architecture-required metrics in TruCon using Python's `logging` module with key-value fields.
- Add `created_at` column to `commit_queue` table (DDL migration) to enable accurate `confirmation_lag` measurement. Currently `updated_at` is overwritten on every status change, losing the original creation timestamp.
- Instrument `/commit` handler with `time.perf_counter()` to measure `commit_latency` (including lock wait time).
- Instrument submit daemon tick with timing to measure `submit_latency` (SUBMITTING → CONFIRMED/FAILED).
- Add `idempotency_hit_count` log emission when the dedup code path returns a cached response.
- Add aggregate `retry_count` query (`SUM(retry_count)`) to `get_queue_stats()`.
- Existing metrics already queryable via `GET /status` (`queue_depth`, `terminal_failure_count`) gain structured log emission on each daemon tick for time-series visibility.

## Capabilities

### New Capabilities
- `trucon-observability`: Defines the 7 required metrics, their semantics, emission points, and structured log format.

### Modified Capabilities
- `trucon-latest-state`: The `GET /status` response gains a `total_retry_count` field from the new aggregate query.

## Impact

- **Code**: `src/tc_api/trucon/app.py` (handler timing, daemon timing, log emissions), `src/tc_api/trucon/database.py` (migration for `created_at`, aggregate retry query).
- **Schema**: `commit_queue` table gains `created_at TEXT` column (backward-compatible ALTER TABLE, nullable with migration backfill from `updated_at`).
- **API**: `GET /status` response adds `total_retry_count: int` field (additive, non-breaking).
- **No new dependencies**: Uses standard `logging` module already in use.
- **Tests**: New tests for metric log emissions, `created_at` migration, timing instrumentation.

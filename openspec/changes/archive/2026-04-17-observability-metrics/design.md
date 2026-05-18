## Context

TruCon is a single-worker FastAPI sequencer (port 8001) with a background submit daemon thread. All 7 architecture-required metrics originate from TruCon internals: the `/commit` handler, the submit daemon, and the SQLite `commit_queue` table. The codebase uses Python's standard `logging` module with a consistent `logger = logging.getLogger("trucon")` pattern. No metrics library is currently active.

The `commit_queue` table has `updated_at` and `confirmed_at` columns but no `created_at`. Since `updated_at` is overwritten on every status transition, the original record creation timestamp is lost after the first state change, making `confirmation_lag` impossible to compute accurately.

## Goals / Non-Goals

**Goals:**
- Emit structured log lines for all 7 architecture-required metrics at appropriate points in TruCon
- Add `created_at` column to `commit_queue` for accurate latency measurement
- Add `total_retry_count` aggregate to `GET /status` response
- All metric emissions testable via log capture in pytest

**Non-Goals:**
- Prometheus `/metrics` endpoint or pull-based metrics (may add later)
- Grafana dashboards or alerting rules
- Metrics for tc_api (port 8000) — it lacks queue state access
- Per-chain metric breakdowns (future extension)

## Decisions

### D1: Structured logging over Prometheus

Use `logger.info()` with key-value fields for all metric emissions. No new dependencies.

**Rationale**: TruCon is single-worker, no multi-process aggregation needed. The `logging` module is already in use everywhere. Prometheus client is in `requirements.txt` but commented out — can be added later if pull-based scraping is needed.

**Alternative considered**: Prometheus `prometheus_client` counters/gauges/histograms — rejected for now because it adds dependency complexity for a system that may only need log-based monitoring initially.

### D2: commit_latency measures full handler time (including lock wait)

`time.perf_counter()` is captured at the top of the `/commit` handler, before `_sequencer_lock` acquisition. The elapsed time includes lock contention, idempotency check, RTMR extend, SQLite insert, and chain state update.

**Rationale**: Callers experience the full latency including lock wait. A commit that takes 5ms of work but 200ms of lock wait is a 205ms commit from the caller's perspective. This is the operationally useful number.

**Alternative considered**: Measure only inside the lock — rejected because it hides contention, which is the primary scaling bottleneck.

### D3: Add `created_at` column via DDL migration

Add `ALTER TABLE commit_queue ADD COLUMN created_at TEXT` in the existing `_migrate_legacy_schema()` function. For existing rows, backfill `created_at = updated_at` (best-effort approximation). New inserts set `created_at = datetime.utcnow().isoformat()` at INSERT time and never update it.

**Rationale**: `confirmation_lag = confirmed_at - created_at` requires the original creation timestamp. Without a dedicated column, `updated_at` is overwritten on SUBMITTING/FAILED_RETRYABLE transitions, making the metric incorrect.

### D4: Daemon emits gauge-like metrics each tick

At the end of each `_submit_daemon_tick()`, emit a single structured log line with snapshot metrics: `queue_depth`, `submitting_count`, `failed_retryable_count`, `failed_terminal_count`, `total_retry_count`. This provides periodic time-series samples without a separate metrics endpoint.

**Rationale**: The daemon already polls the queue every cycle. Adding a log line with current stats is nearly free and gives log-based monitoring a regular heartbeat.

### D5: Metric log format

All metric log lines use a consistent format with `metric=` prefix for easy grep/filter:

```
logger.info("metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s", ...)
logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", ...)
logger.info("metric=idempotency_hit key=%s chain_id=%s record_id=%s", ...)
logger.info("metric=queue_snapshot queue_depth=%d submitting=%d failed_retryable=%d failed_terminal=%d total_retries=%d", ...)
```

## Risks / Trade-offs

- **[Log volume]** → Daemon tick logs emit every cycle (default 1s). Mitigated: single line per tick, operators can filter by `metric=queue_snapshot` or adjust daemon interval.
- **[created_at backfill approximation]** → Existing rows get `created_at = updated_at`, which may overstate confirmation_lag for records that went through state transitions before migration. Mitigated: only affects pre-migration records, not new ones.
- **[No aggregation]** → Structured logs require external tooling (grep, ELK, Loki) to build dashboards. Mitigated: acceptable for current scale; Prometheus can be layered on later without changing emission points.

## Migration Plan

1. `_migrate_legacy_schema()` runs on startup — adds `created_at` column if missing.
2. Backfill: `UPDATE commit_queue SET created_at = updated_at WHERE created_at IS NULL`.
3. No rollback needed — column is additive, NULL-safe, doesn't affect existing queries.

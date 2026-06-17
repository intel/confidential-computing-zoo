## 1. Docktap Sweeper and Routing-State Retention

- [x] 1.1 Add Docktap-owned periodic sweeper startup and shutdown handling in `docktap/main.py`
- [x] 1.2 Wire `OperationTracker.cleanup_old_operations()` into the sweeper using a configurable last-access retention window
- [x] 1.3 Extend `WorkloadStore` schema and API with `last_seen_at`, `removed_at`, and `last_operation` lifecycle fields
- [x] 1.4 Update Docktap lifecycle handling so `create`, `start`, `stop`, and `rm` refresh or transition workload-mapping rows correctly
- [x] 1.5 Implement removed-container mapping cleanup based on `removed_at` plus a configurable grace window

## 2. Retry-State Retention and Configuration

- [x] 2.1 Add explicit Docktap retention configuration for sweeper interval, operation retention, removed-container retention, acknowledged retry retention, and terminal retry retention
- [x] 2.2 Extend Docktap retry bookkeeping so retryable items remain ineligible for GC while pending
- [x] 2.3 Implement sweeper cleanup for acknowledged retry records after the configured short diagnostic window
- [x] 2.4 Implement sweeper cleanup for terminally failed retry records after the configured operator window
- [x] 2.5 Add focused tests for lifecycle-aware workload mapping cleanup and retry-state retention boundaries

## 3. Runbook and Change Closure

- [x] 3.1 Update Docktap operational documentation to describe local retention behavior, tuning knobs, and replay expectations
- [x] 3.2 Replace the obsolete legacy-fallback migration guidance with TruCon-only rollout, supervision, parity-check, and degraded-mode runbook steps
- [x] 3.3 Rewrite the remaining `introduce-trucon-event-orchestrator` task 5.3 so it reflects the new runbook closure work instead of a removed legacy fallback
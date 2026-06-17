## Why

Docktap now documents daemon/internal taxonomy, normalized task transitions, API/internal correlation, and secondary runtime interpretation, but mixed Docker traces still do not explain how post-runtime housekeeping activity should be interpreted once primary and secondary runtime sequences have finished. The project needs that boundary now so daemon maintenance lines such as exec cleanup are not confused with workload lifecycle regressions, while broader maintenance taxonomy and parser design remain separately scoped.

## What Changes

- Define a documentation-first interpretation contract for daemon/internal housekeeping and maintenance activity in mixed Docker traces.
- Define the first-wave housekeeping scope conservatively around post-exec cleanup and similar post-runtime maintenance context rather than a broad maintenance taxonomy.
- Document how housekeeping activity should be read relative to primary lifecycle and secondary runtime activity, including its usual role as expected maintenance noise.
- Define a minimal first-wave boundary for when housekeeping patterns become investigation-worthy signals without introducing scoring models or alerting rules.
- Reserve extension room for later maintenance families such as image GC, background scanning, and retry or reconcile loops without treating them as fully specified in this change.
- Explicitly defer parser implementation, machine confidence, Docktap-local retention semantics, and broad maintenance coverage beyond the first-wave contract.

## Capabilities

### New Capabilities
- `daemon-housekeeping-maintenance-interpretation`: Defines the documentation contract for interpreting daemon/internal housekeeping and post-runtime maintenance activity in mixed Docker traces.

### Modified Capabilities
- None.

## Impact

- Affected docs: `docs/docktap/architecture.md`, `docs/docktap/api.md`, `docs/overview_tasks.md`, and mixed-trace or runbook material derived from `openclaw-docker-analysis.md`.
- Affected systems: operator interpretation of mixed Docker traces and future GAP-22 planning for broader maintenance taxonomy, parser-facing modeling, and anomaly handling.
- Dependencies: builds on `daemon-internal-phase-taxonomy`, `daemon-api-internal-correlation`, and `daemon-secondary-runtime-interpretation`, while leaving Docktap runtime code paths and HTTP request classification unchanged.
## 1. Secondary Runtime Interpretation Contract

- [x] 1.1 Update `docs/docktap/architecture.md` to define healthcheck-like exec flows as secondary runtime activity built on the normalized exec-task spine.
- [x] 1.2 Update `docs/docktap/api.md` to document the operator-facing interpretation contract for secondary exec flows and conservative healthcheck-like classification.

## 2. Attach Meaning, Sequences, And Anomalies

- [x] 2.1 Document in the affected Docktap docs that `attach: stdout/stderr begin/end` and `attach done` are stream or transport context around exec flows rather than workload lifecycle states.
- [x] 2.2 Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing the healthy healthcheck-like sequence with required exec-task evidence and contextual attach or result evidence.
- [x] 2.3 Document the first-wave anomalous secondary-runtime shapes, including repeated exec failures and missing exit or attach completion cues, while keeping housekeeping cleanup guidance deferred.

## 3. Planning Sync

- [x] 3.1 Update `docs/overview_tasks.md` so `GAP-22.4` reflects the documentation-first secondary-runtime interpretation scope and stays clearly separated from `GAP-22.5`.
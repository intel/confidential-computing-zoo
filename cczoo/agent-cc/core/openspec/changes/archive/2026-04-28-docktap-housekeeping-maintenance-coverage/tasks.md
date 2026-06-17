## 1. Housekeeping Interpretation Contract

- [x] 1.1 Update `docs/docktap/architecture.md` to define daemon/internal housekeeping as post-runtime maintenance context distinct from primary lifecycle and secondary runtime activity.
- [x] 1.2 Update `docs/docktap/api.md` to document the operator-facing housekeeping interpretation contract and its separation from Docktap-local cleanup semantics.

## 2. Scope Boundaries, Correlation, And Signals

- [x] 2.1 Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing post-exec cleanup as first-wave housekeeping evidence and where it sits relative to nearby runtime activity.
- [x] 2.2 Document in the affected Docktap docs that first-wave housekeeping coverage is centered on exec-cleanup-style evidence, while broader maintenance families remain future extension room.
- [x] 2.3 Document the contextual-first correlation model for housekeeping activity and the minimal boundary between expected maintenance noise and investigation-worthy housekeeping patterns.

## 3. Planning Sync

- [x] 3.1 Update `docs/overview_tasks.md` so `GAP-22.5` reflects the narrower first-wave housekeeping interpretation scope and stays clearly separated from Docktap-local retention/GC concerns.
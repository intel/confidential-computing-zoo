## 1. Cross-Plane Correlation Rules

- [x] 1.1 Update `docs/docktap/architecture.md` to define the documentation-first correlation contract between API-path observations and normalized daemon/internal transitions.
- [x] 1.2 Update `docs/docktap/api.md` to document the primary correlation shapes for container create/start flows and exec flows.

## 2. Evidence Tiers And Examples

- [x] 2.1 Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing how API observations correlate to normalized internal transitions.
- [x] 2.2 Document tiered join evidence and ambiguity handling in the affected Docktap docs, distinguishing stronger identifiers from contextual and fallback evidence.
- [x] 2.3 Update the affected docs to make the defer boundary explicit for parser implementation, healthcheck intent, attach-stream semantics, and housekeeping guidance.

## 3. Planning Sync

- [x] 3.1 Update `docs/overview_tasks.md` so `GAP-22.3` reflects the narrower correlation-contract scope and stays clearly separated from `GAP-22.4` and `GAP-22.5`.

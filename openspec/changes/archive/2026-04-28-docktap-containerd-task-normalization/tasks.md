## 1. Normalized Task-Transition Contract

- [x] 1.1 Update `docs/docktap/architecture.md` to define the normalized containerd task-transition model inside the daemon/internal `task lifecycle` family.
- [x] 1.2 Update `docs/docktap/api.md` to document the first-wave normalized transition set and the minimum canonical daemon/internal facts for those transitions.

## 2. Scope Boundaries And Examples

- [x] 2.1 Add representative mixed-trace examples from `openclaw-docker-analysis.md` showing container-task and exec-task transitions in normalized form.
- [x] 2.2 Update the affected docs to make the defer boundary explicit for API/internal correlation, healthcheck interpretation, attach-stream modeling, and parser or ingestion implementation.

## 3. Planning Sync

- [x] 3.1 Update `docs/overview_tasks.md` so `GAP-22.2` reflects the normalized task-transition contract scope and stays clearly separated from `GAP-22.3` and `GAP-22.4`.

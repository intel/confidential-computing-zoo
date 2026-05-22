## 1. Taxonomy Documentation

- [x] 1.1 Update `docs/docktap/architecture.md` to introduce daemon/runtime-internal phases as a second observation plane alongside the existing API-path observation model.
- [x] 1.2 Document the five top-level daemon/internal phase families in the relevant Docktap docs: storage/mount, runtime-spec/bundle, task lifecycle, attach/stream, and housekeeping.

## 2. Example Mapping And Scope Boundaries

- [x] 2.1 Add representative mappings from `openclaw-docker-analysis.md` showing how each top-level phase family appears in a mixed trace.
- [x] 2.2 Update the affected docs to make the defer boundary explicit for event normalization, API/internal correlation, healthcheck disambiguation, and housekeeping anomaly guidance.
## 1. Exec Classification Contract

- [x] 1.1 Add explicit `exec_create` and `exec_start` classification for `POST /containers/{id}/exec` and `POST /exec/{id}/start`.
- [x] 1.2 Preserve minimal exec-path identifiers in operation metadata without changing lifecycle parent-linking or `SUBMITTABLE_OPERATIONS`.

## 2. Focused Coverage and Docs

- [x] 2.1 Add focused tests for the minimal exec create/start flow, including stable label and identifier expectations.
- [x] 2.2 Update Docktap architecture/API docs to distinguish exec observation labels from lifecycle commit labels and to document deferred exec inspection paths.
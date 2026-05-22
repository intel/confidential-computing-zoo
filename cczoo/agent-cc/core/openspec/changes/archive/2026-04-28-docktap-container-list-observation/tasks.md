## 1. Classification Contract

- [x] 1.1 Add a `container_list` classification for `GET /containers/json` and `GET /v*/containers/json`.
- [x] 1.2 Preserve query parameters for container-list requests without changing the existing request parsing contract.

## 2. Tests and Documentation

- [x] 2.1 Add focused tests for versioned and unversioned `/containers/json` requests, including `all=1` coverage.
- [x] 2.2 Update Docktap architecture/API docs to distinguish `container_list` from `inspect` and to state that list traffic does not affect lifecycle submission or parent-linking.
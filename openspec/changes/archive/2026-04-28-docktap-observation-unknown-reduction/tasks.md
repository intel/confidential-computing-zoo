## 1. Observation Classification Update

- [x] 1.1 Extend the Docktap path classifier so `GET /v*/containers/{id}/logs` is recorded as an explicit read-only observation type instead of `unknown`.
- [x] 1.2 Keep streaming timeout behavior and trusted lifecycle submission boundaries unchanged while introducing the new logs observation label.

## 2. Verification and Boundary Documentation

- [x] 2.1 Add focused tests covering versioned and unversioned container-log paths and preserving current streaming detection behavior.
- [x] 2.2 Update Docktap architecture/API docs to list the new logs observation class and document which remaining read-only endpoints are intentionally deferred in the `unknown` bucket.
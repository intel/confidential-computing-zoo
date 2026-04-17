## 1. TruCon Commit Client Module

- [x] 1.1 Create `docktap/trucon_client.py` with `TruConCommitter` class that takes a TruCon URL and provides a `submit_operation(op_record, operation_type)` method
- [x] 1.2 Implement Entry mapping logic: convert `OperationRecord` fields to `Entry(key, value)` pairs per operation type (pull, create, start, stop, rm) as defined in design decision #4
- [x] 1.3 Implement DSSE signing: import digest functions from `tc_api.tlog_client`, build In-Toto statement, sign with Sigstore using `detect_credential()`
- [x] 1.4 Implement HTTP POST to TruCon `/commit` with `chain_id="default"`, event_digest, event_id, and idempotency_key; 5-second timeout
- [x] 1.5 Implement best-effort error handling: catch all exceptions (network, signing, HTTP errors), log warning with operation type and error details, return failure indicator without raising

## 2. Proxy Integration

- [x] 2.1 Add `SUBMITTABLE_OPERATIONS` set (`pull`, `create`, `start`, `stop`, `rm`) and operation-type filter check
- [x] 2.2 Hook `TruConCommitter.submit_operation()` into `DockerProxyServer.handle_client()` after `enrich_from_response()` / `log_operation_json()` and before `client_socket.close()`
- [x] 2.3 Add TruCon URL configuration (environment variable `TRUCON_URL`, default `http://127.0.0.1:8001`)
- [x] 2.4 Initialize `TruConCommitter` in `SockBridge.__init__()` and pass to `DockerProxyServer`

## 3. Unit Tests

- [x] 3.1 Test Entry mapping for each operation type: verify correct key/value pairs are constructed from OperationRecord fixtures
- [x] 3.2 Test operation type filtering: verify only pull/create/start/stop/rm pass the `SUBMITTABLE_OPERATIONS` gate
- [x] 3.3 Test best-effort failure handling: mock TruCon as unreachable, verify warning logged and no exception raised
- [x] 3.4 Test DSSE bundle construction: verify predicate type, digest computation, and subject format match tc_api conventions

## 4. Integration Tests

- [x] 4.1 Test concurrent Docktap and REST submissions: both submit to `chain_id="default"` and receive monotonically increasing `sequence_num` values
- [x] 4.2 Test end-to-end Docktap proxy flow: Docker CLI → proxy → Docker daemon → response returned → TruCon commit verified in queue

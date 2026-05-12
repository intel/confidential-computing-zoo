## 1. Workload Store Module

- [x] 1.1 Create `docktap/workload_store.py` with `WorkloadStore` class: `init_db()`, `put(container_id, workload_id)`, `get(container_id) -> Optional[str]`
- [x] 1.2 SQLite schema: `container_workload` table (`container_id TEXT PRIMARY KEY, workload_id TEXT NOT NULL, created_at TEXT NOT NULL`) at `/dev/shm/docktap/container_map.db`
- [x] 1.3 `init_db()` creates directory and table if not exist, preserves existing data on restart

## 2. Label Extraction

- [x] 2.1 Add `_extract_workload_id(params: dict) -> Optional[str]` to `docktap/proxy/docker_proxy.py` that parses `io.trucon.workload-id` from the create request body's `Labels` dict, returning `None` if absent or empty
- [x] 2.2 Call `_extract_workload_id` during `create` operation processing and pass the result through to the TruCon committer

## 3. Dynamic Chain Routing

- [x] 3.1 Update `TruConCommitter.__init__` to accept and store a `WorkloadStore` instance
- [x] 3.2 Update `TruConCommitter._do_submit` to resolve `chain_id` from `WorkloadStore.get(container_id)` for `start`/`stop`/`rm`, and from extracted label for `create`; fall back to `"default"` when no mapping exists
- [x] 3.3 On `create` with a resolved workload_id, call `WorkloadStore.put(container_id, workload_id)` to persist the mapping
- [x] 3.4 `pull` operations always use `chain_id="default"` (no change from current behavior)

## 4. Startup Integration

- [x] 4.1 Initialize `WorkloadStore` in `docktap/main.py` and pass it to `DockerProxyServer` / `TruConCommitter`
- [x] 4.2 Call `WorkloadStore.init_db()` during Docktap startup

## 5. Tests

- [x] 5.1 Unit tests for `WorkloadStore`: create, read, restart recovery, missing key fallback, empty value handling
- [x] 5.2 Unit tests for `_extract_workload_id`: label present, label absent, label empty, malformed body
- [x] 5.3 Integration tests for chain routing: create with label → start resolves chain, create without label → default chain, Docktap restart → mapping preserved
- [x] 5.4 Update existing `docktap/tests/test_trucon_client.py` tests that assert `chain_id="default"` to account for dynamic resolution

## 6. Regression

- [x] 6.1 Run full test suite (`bash run_tests.sh`) and verify no regressions

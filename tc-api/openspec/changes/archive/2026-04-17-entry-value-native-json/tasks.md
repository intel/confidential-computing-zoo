## 1. Core Type Change

- [x] 1.1 Change `Entry.value` type annotation from `str` to `Any` in `src/tc_api/tlog/types.py`
- [x] 1.2 Update `compute_entry_digest()` signature in `src/tc_api/tlog_client.py` from `(str, str)` to `(str, Any)`

## 2. REST API Call Sites (remove json.dumps wrappers)

- [x] 2.1 Update all `add_entry()` calls in `src/tc_api/main.py` to pass native values instead of `json.dumps()` strings
- [x] 2.2 Update all `add_entry()` calls in `src/tc_api/services.py` to pass native values instead of `json.dumps()` strings
- [x] 2.3 Fix typo `"verfiy_sbom_status"` → `"verify_sbom_status"` in `src/tc_api/main.py`

## 3. Docktap Unification

- [x] 3.1 Import `Entry` from `tc_api.tlog.types` in `docktap/trucon_client.py`
- [x] 3.2 Refactor `_build_entries()` to return `List[Entry]` with native values instead of `List[Tuple[str, str]]` with `json.dumps()` values
- [x] 3.3 Update `_build_commit_payload()` to serialize `Entry` objects into the DSSE predicate

## 4. Tests

- [x] 4.1 Update `tests/test_two_level_digest.py` — adjust entry construction and expected digest values for native value encoding
- [x] 4.2 Update focused unit modules such as `tests/test_tdx_mr_adapter.py` — fix any Entry construction that uses `json.dumps()` wrappers
- [x] 4.3 Update Docktap tests in `docktap/tests/` — adjust for `Entry` objects and native values
- [x] 4.4 Run full regression suite (`bash run_tests.sh`) and verify all tests pass

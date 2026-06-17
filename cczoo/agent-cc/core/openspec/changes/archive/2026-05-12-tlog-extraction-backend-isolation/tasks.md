## 1. Create tlog standalone package

- [x] 1.1 Create `tlog/` directory with `pyproject.toml` (name=tlog, src layout, zero third-party deps)
- [x] 1.2 Copy `src/tc_api/tlog/types.py` → `tlog/src/tlog/types.py` (no changes)
- [x] 1.3 Copy `src/tc_api/tlog/errors.py` → `tlog/src/tlog/errors.py` (no changes)
- [x] 1.4 Copy `src/tc_api/tlog/local_mr.py` → `tlog/src/tlog/local_mr.py` (no changes)
- [x] 1.5 Copy `src/tc_api/tlog/immutable.py` → `tlog/src/tlog/immutable.py`, change `submit_bundle` parameter from `Bundle` to `str`, remove `sigstore.models` import
- [x] 1.6 Create `tlog/src/tlog/digest.py` — consolidate `canonical_json`, `compute_entry_digest`, `compute_event_digest` from `tlog_client.py`
- [x] 1.7 Create `tlog/src/tlog/__init__.py` with re-exports of all public types, errors, ABCs, and digest functions
- [x] 1.8 Verify `pip install -e tlog/` succeeds in a clean venv with zero third-party deps

## 2. Create tlog-rekor backend package

- [x] 2.1 Create `tlog-rekor/` directory with `pyproject.toml` (name=tlog-rekor, depends on tlog + sigstore + rekor-types + cryptography)
- [x] 2.2 Move `src/tc_api/trucon/adapters/sigstore.py` → `tlog-rekor/src/tlog_rekor/adapter.py`, update imports: `from tlog.immutable import ImmutableLogAdapter`, change `submit_bundle` to accept `str` and deserialize to `Bundle` internally
- [x] 2.3 Move `src/tc_api/trucon/adapters/oci_mirror.py` → `tlog-rekor/src/tlog_rekor/oci_mirror.py`, update imports
- [x] 2.4 Create `tlog-rekor/src/tlog_rekor/__init__.py` with exports
- [x] 2.5 Verify `pip install -e tlog-rekor/` succeeds with tlog installed

## 3. Scaffold tlog-onchain package

- [x] 3.1 Create `tlog-onchain/` directory with `pyproject.toml` (name=tlog-onchain, depends on tlog)
- [x] 3.2 Create `tlog-onchain/src/tlog_onchain/adapter.py` with `OnChainLogAdapter` stub raising `NotImplementedError`
- [x] 3.3 Create `tlog-onchain/src/tlog_onchain/__init__.py`

## 4. Update tc-api dependencies and adapter loading

- [x] 4.1 Update `pyproject.toml` to add `tlog` and `tlog-rekor` as dependencies
- [x] 4.2 Remove `sigstore.py` and `oci_mirror.py` from `src/tc_api/trucon/adapters/` (already moved)
- [x] 4.3 Update TruCon submit daemon in `trucon/app.py` to load adapter via `TC_IMMUTABLE_BACKEND` env var with conditional import from `tlog_rekor.adapter`
- [x] 4.4 Update `SigstoreLogAdapter` call sites in `trucon/app.py` to pass `str` bundle instead of `Bundle` object

## 5. Consolidate digest function duplicates

- [x] 5.1 Update `tlog_client.py` to import `canonical_json`, `compute_entry_digest`, `compute_event_digest` from `tlog.digest`, remove local definitions
- [x] 5.2 Update `sigstore_baseline.py` to import from `tlog.digest`, remove `_canonical_json`, `_compute_entry_digest`, `_compute_event_digest`
- [x] 5.3 Update `trucon/owner_attestation.py` to import `canonical_json` from `tlog.digest`, remove local definition

## 6. Add compatibility shims

- [x] 6.1 Replace `src/tc_api/tlog/types.py` with shim: `from tlog.types import *`
- [x] 6.2 Replace `src/tc_api/tlog/immutable.py` with shim: `from tlog.immutable import *`
- [x] 6.3 Replace `src/tc_api/tlog/errors.py` with shim: `from tlog.errors import *`
- [x] 6.4 Replace `src/tc_api/tlog/local_mr.py` with shim: `from tlog.local_mr import *`
- [x] 6.5 Update `src/tc_api/tlog/__init__.py` to re-export from `tlog` package
- [x] 6.6 Verify all existing tests pass with shims in place

## 7. Migrate import paths in tc_api source

- [x] 7.1 Update `main.py` imports: `from tc_api.tlog.*` → `from tlog.*`
- [x] 7.2 Update `services.py` imports: `from tc_api.tlog.*` → `from tlog.*`
- [x] 7.3 Update `tlog_client.py` imports: `from tc_api.tlog.*` → `from tlog.*`
- [x] 7.4 Update `trucon/app.py` imports: `from tc_api.tlog.*` → `from tlog.*`
- [x] 7.5 Update `trucon/adapters/tdx_mr.py` import: `from tc_api.tlog.local_mr` → `from tlog.local_mr`
- [x] 7.6 Update `docktap/trucon_client.py` imports: `from tc_api.tlog.*` → `from tlog.*`
- [x] 7.7 Update `cli/verify.py`: `from tc_api.trucon.adapters.sigstore` → `from tlog_rekor.adapter`
- [x] 7.8 Update remaining tc_api source files referencing old import paths

## 8. Migrate import paths in tests

- [x] 8.1 Update test files importing `from tc_api.tlog.*` → `from tlog.*` (batch grep-replace)
- [x] 8.2 Update test files importing `SigstoreLogAdapter` from old path → `from tlog_rekor.adapter`
- [x] 8.3 Update mock/patch targets in tests to reference new module paths
- [x] 8.4 Run full test suite and fix any remaining import failures

## 9. Remove compatibility shims

- [x] 9.1 Delete shim contents from `src/tc_api/tlog/types.py`, `immutable.py`, `errors.py`, `local_mr.py`
- [x] 9.2 Update `src/tc_api/tlog/__init__.py` to remove re-exports (or delete if empty)
- [x] 9.3 Run full test suite to confirm no remaining references to old paths

## 10. Validation

- [x] 10.1 Verify `pip install -e tlog/ && pip install -e tlog-rekor/ && pip install -e .` works from tc-api
- [x] 10.2 Run `pytest tests/` — all existing tests pass
- [x] 10.3 Verify `cli/verify` works with only `tlog` + `tlog-rekor` installed (no trucon import needed for verification)
- [x] 10.4 Verify digest output consistency: same inputs produce identical digests before and after migration

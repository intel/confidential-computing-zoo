## 1. Create target directory structure

- [x] 1.1 Create `src/tc_api/tlog/` package with `__init__.py`
- [x] 1.2 Create `src/tc_api/trucon/` package with `__init__.py`
- [x] 1.3 Create `src/tc_api/trucon/adapters/` package with `__init__.py`

## 2. Move leaf domain files to tlog/

- [x] 2.1 Move `trusted_container_log/types.py` → `tlog/types.py` (no changes needed)
- [x] 2.2 Move `trusted_container_log/errors.py` → `tlog/errors.py` (no changes needed)

## 3. Split ABC/implementation files

- [x] 3.1 Extract `LocalMRAdapter` ABC from `trusted_container_log/local_mr.py` → `tlog/local_mr.py`; move `TdxMRAdapter` impl → `trucon/adapters/tdx_mr.py` with import from `tc_api.tlog.local_mr`
- [x] 3.2 Extract `ImmutableLogAdapter` ABC from `trusted_container_log/tlog_impl.py` → `tlog/immutable.py`; move `SigstoreLogAdapter` impl → `trucon/adapters/sigstore.py` with import from `tc_api.tlog.immutable`

## 4. Move service files to trucon/

- [x] 4.1 Move `trusted_container_log/database.py` → `trucon/database.py`; replace `from ..config import` with module-level defaults and environment variable override
- [x] 4.2 Move `src/tc_api/trucon.py` → `trucon/app.py`; update internal imports to use relative imports within `trucon/` and `tc_api.tlog` for shared types

## 5. Move client module

- [x] 5.1 Move `trusted_container_log/api.py` → `src/tc_api/tlog_client.py`; update imports to use `tc_api.tlog.types` and `tc_api.tlog.errors`

## 6. Update tlog/ and trucon/ package exports

- [x] 6.1 Populate `tlog/__init__.py` with public exports (Entry, ChainState, CommitResult, TLogError, etc.)
- [x] 6.2 Populate `trucon/__init__.py` with `app` reference for uvicorn entry point
- [x] 6.3 Populate `trucon/adapters/__init__.py` (can be empty or re-export adapters)

## 7. Update consumer imports

- [x] 7.1 Update `src/tc_api/main.py` imports: `TrustedLogAPI` from `tlog_client`, `Entry` from `tlog.types`, `SigstoreLogAdapter` from `trucon.adapters.sigstore`
- [x] 7.2 Update `src/tc_api/services.py` imports: `TrustedLogAPI` from `tlog_client`, `Entry`/`CommitResult` from `tlog.types`

## 8. Update entry points and startup scripts

- [x] 8.1 Update `start.sh` TruCon uvicorn entry point to `tc_api.trucon.app:app`
- [x] 8.2 Update any references in `pyproject.toml`, `Dockerfile`, `docker-compose.yml` to the new module paths
- [x] 8.3 Update `scripts/trust_service.sh` and `aa_asr_cdh/trust_service.sh` if they reference old module paths

## 9. Remove legacy package

- [x] 9.1 Delete `src/tc_api/trusted_container_log/` directory entirely

## 10. Validate and fix tests

- [x] 10.1 Update test imports in `tests/test_tlog_impl.py`, `tests/test_tlog_refactored.py`, and focused unit modules such as `tests/test_tdx_mr_adapter.py`
- [x] 10.2 Run focused unit coverage (`pytest tests/test_tdx_mr_adapter.py -v`) and fix any import or runtime errors
- [x] 10.3 Run `bash run_tests.sh` for full validation

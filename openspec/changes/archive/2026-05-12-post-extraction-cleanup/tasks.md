## 1. Delete dead adapter files

- [x] 1.1 Delete `src/tc_api/trucon/adapters/sigstore.py` (dead duplicate of `tlog-rekor/src/tlog_rekor/adapter.py`)
- [x] 1.2 Delete `src/tc_api/trucon/adapters/oci_mirror.py` (dead duplicate of `tlog-rekor/src/tlog_rekor/oci_mirror.py`)
- [x] 1.3 Update `tests/test_oci_bundle_mirror.py`: change `from tc_api.trucon.adapters.oci_mirror import ...` → `from tlog_rekor.oci_mirror import ...`
- [x] 1.4 Update `tests/test_real_oci_mirror_integration.py`: same import migration
- [x] 1.5 Update `tests/test_real_rekor_integration.py`: same import migration for OciBundleMirror
- [x] 1.6 Update `tests/test_tlog_impl.py`: same import migration for OciBundleMirror
- [x] 1.7 Verify no remaining imports of `tc_api.trucon.adapters.sigstore` or `tc_api.trucon.adapters.oci_mirror` in the codebase

## 2. Delete orphan tlog shim files

- [x] 2.1 Delete `src/tc_api/tlog/types.py`
- [x] 2.2 Delete `src/tc_api/tlog/errors.py`
- [x] 2.3 Delete `src/tc_api/tlog/immutable.py`
- [x] 2.4 Delete `src/tc_api/tlog/local_mr.py`
- [x] 2.5 Verify `src/tc_api/tlog/__init__.py` contains only the tombstone notice (no re-exports)
- [x] 2.6 Verify no code imports from `tc_api.tlog.types`, `tc_api.tlog.errors`, etc.

## 3. Move docktap into src/tc_api/

- [x] 3.1 Move `docktap/` directory to `src/tc_api/docktap/` (preserve full tree: proxy/, tests/, tools/)
- [x] 3.2 Verify `src/tc_api/docktap/__init__.py` exists and package is discoverable

## 4. Rewrite docktap internal imports

- [x] 4.1 `main.py`: remove `sys.path.insert` hack, convert `from trucon_client import ...` → `from .trucon_client import ...`, `from proxy.* import ...` → `from .proxy.* import ...`, `from workload_store import ...` → `from .workload_store import ...`
- [x] 4.2 `proxy/docker_proxy.py`: convert `from trucon_client import ...` → `from ..trucon_client import ...`
- [x] 4.3 `tests/conftest.py`: remove `sys.path.insert` hack
- [x] 4.4 `tests/test_proxy.py`: remove `sys.path.insert` hack, convert bare imports to relative or `tc_api.docktap.*`
- [x] 4.5 `tests/test_trucon_client.py`: convert bare imports (`from trucon_client import ...`, `from proxy.operation_log import ...`) to `tc_api.docktap.*`
- [x] 4.6 `tests/test_docktap_integration.py`: convert bare imports to `tc_api.docktap.*`, update `tc_api.trucon.database` import if needed
- [x] 4.7 `tests/test_workload_chain_routing.py`: convert bare imports to `tc_api.docktap.*`
- [x] 4.8 `tests/test_lifecycle_classification.py`: convert bare imports to `tc_api.docktap.*`
- [x] 4.9 `tests/test_proxy_response_handling.py`: convert bare imports to `tc_api.docktap.*`
- [x] 4.10 `tests/test_workload_store.py`: convert bare imports to `tc_api.docktap.*`
- [x] 4.11 `stream_test.py`: remove `sys.path.insert` hack if present, convert bare imports
- [x] 4.12 Verify no `sys.path.insert` or `sys.path.append` calls remain in any `src/tc_api/docktap/` file

## 5. Update entry points and deployment

- [x] 5.1 Add `tc-docktap = "tc_api.docktap.main:main"` to `pyproject.toml` `[project.scripts]`
- [x] 5.2 Ensure `tc_api/docktap/main.py` has a `main()` function callable as entry point
- [x] 5.3 Update `docker-compose.yml`: change docktap command from `docktap.main` to `tc_api.docktap.main`
- [x] 5.4 Update `start.sh`: change `python -m docktap.main` to `python -m tc_api.docktap.main`
- [x] 5.5 Update `start.sh` process matching pattern for docktap (grep for `docktap.main`)
- [x] 5.6 Grep for any remaining references to `docktap.main` (without `tc_api.` prefix) in scripts/, docs/, and root files

## 6. Validation

- [x] 6.1 Run `pip install -e .` and verify `tc-docktap --help` works
- [x] 6.2 Run `python -m tc_api.docktap.main --help` and verify it works
- [x] 6.3 Run docktap tests: `pytest src/tc_api/docktap/tests/ -v`
- [x] 6.4 Run full test suite: `pytest tests/ -v` — verify no regressions
- [x] 6.5 Verify no remaining imports of `tc_api.trucon.adapters.sigstore` or `tc_api.trucon.adapters.oci_mirror`
- [x] 6.6 Verify no remaining bare `from trucon_client import` or `from proxy.` imports outside docktap

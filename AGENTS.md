# Project Guidelines

## Build and Test
- Setup environment: `bash setup.sh` (creates `venv`, installs the package in editable mode, initializes directories).
- Start service: `bash start.sh` (recommended; validates tool availability and runs `uvicorn`).
- Alternate start: `python -m tc_api.main`.
- Run all tests: `bash run_tests.sh`.
- Run manual API checks: `python -m tests.test_api` (or `python -m tests.test_api health|build|publish|register`).
- Run automated tests: `pytest tests/test_unit.py -v`.

## Architecture
- API layer: `src/tc_api/main.py` defines FastAPI endpoints and request flow.
- Data contracts: `src/tc_api/models.py` contains request/response and status models.
- Service layer: `src/tc_api/services.py` encapsulates build/publish/launch workflows and external CLI calls.
- KBS integration: `src/tc_api/kbs_service.py` wraps key registration/lookup behavior.
- Trusted-log shared types: `tlog/` is a standalone package (zero deps) with domain types, ABCs, errors, and digest functions.
- Rekor backend adapter: `tlog-rekor/` is a standalone package with `SigstoreLogAdapter` and `OciBundleMirror`.
- On-chain backend adapter: `tlog-onchain/` is a scaffold package with `OnChainLogAdapter` stub.
- Trusted-log client: `src/tc_api/tlog_client.py` wraps DSSE signing and TruCon communication.
- TruCon service: `src/tc_api/trucon/` contains the sequencer, SQLite queue, and platform adapters.
- Docktap sidecar: `src/tc_api/docktap/` is the Docker operation interception proxy (sub-package of tc_api). Entry point: `tc-docktap` CLI or `python -m tc_api.docktap.main`.
- Runtime config: `src/tc_api/config.py` centralizes environment-driven settings (paths, commands, registry, KBS).
- Tests: `tests/` contains all test files (`test_unit.py`, `test_api.py`, `test_runner.py`, etc.).
- Scripts: `scripts/` contains VFS lifecycle, Windows platform scripts, and container entrypoint helpers.
- Docs: `docs/` contains architecture documentation and trusted-log module docs.

## Conventions
- Prefer extending logic in `src/tc_api/services.py` and keep endpoint handlers in `src/tc_api/main.py` focused on orchestration.
- Persist per-build artifacts under `builds/<build_id>/`; do not scatter output files in repository root.
- Treat `docker`, `cosign`, `syft`, and `skopeo` as external dependencies; surface clear errors when unavailable.
- Preserve status progression fields (`status`, `current_step`, `error_message`) when changing workflows.
- Keep request/response model changes synchronized with endpoint handlers and tests.

## Pitfalls
- Tests and runtime behavior depend on a running local API at `http://localhost:8000` for integration paths.
- Many operations shell out with `subprocess.run`; keep timeouts and stderr/stdout capture intact for debugging.
- Build/publish flows assume filesystem directories (`uploads`, `builds`, `logs`) exist or are created.
- Some flows rely on environment/OIDC availability for Sigstore operations; avoid hardcoding environment-specific settings.

## Docs
- Endpoint behavior and usage examples: `README.md`.
- Test execution details and coverage expectations: `docs/TESTING.md`.
- System architecture: `docs/architecture.md`.
- Docktap architecture: `docs/docktap/architecture.md`.
- Trusted-log module docs: `docs/trusted-log/`.

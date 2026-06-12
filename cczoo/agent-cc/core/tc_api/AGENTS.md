# Project Guidelines

## Build and Test
- Setup environment: `cd tc_api && bash setup.sh` (creates `venv`, installs `tlog[rekor]` and `tc_api` in editable mode).
- Start service: `cd tc_api && ./start.sh restart` (preferred local lifecycle entrypoint for tc_api, TruCon, and Docktap).
- Alternate start: `python -m tc_api.api.app`.
- Run all tests: `cd tc_api && ./run_tests.sh --type all --verbose`.
- Run manual API checks: `python -m tests.test_api` (or `python -m tests.test_api health|build|publish|register`).
- Run automated tests: `pytest tests/test_subprocess_unit.py tests/test_tdx_mr_adapter.py -v`.
- Docker build: `cd tc_api && docker-compose build` (uses `tc_api/docker-compose.yml` and `tc_api/Dockerfile`).

## Repository Layout
- This file lives in `tc_api/`, one of several top-level packages in the monorepo.
- Standalone package at repo root: `tlog/`.
- Trust service: `trust-service/` (attestation agent/CDH).
- Workspace-level files at repo root: `deploy/`, `scripts/dev-up.sh`.
- tc_api deployment files: `tc_api/Dockerfile`, `tc_api/docker-compose.yml`.

## Architecture
- API layer: `tc_api/api/app.py` defines the FastAPI application and registers routers from `tc_api/api/routers/`.
- HTTP workflow helpers: `tc_api/api/workflows.py` contains build/publish/launch request orchestration.
- Data contracts: `tc_api/models.py` contains request/response and status models.
- Service layer: `tc_api/services/` encapsulates build/publish/launch/LUKS encrypted-VFS workflows and external CLI calls.
- KBS integration: `tc_api/kbs_service.py` wraps key registration/lookup behavior.
- Trusted-log shared types: `tlog/` is a standalone package (zero deps) with domain types, ABCs, errors, and digest functions.
- Rekor backend adapter: `tlog/tlog/backends/rekor/` contains `SigstoreLogAdapter` and `OciBundleMirror`.
- On-chain backend adapter: `tlog/tlog/backends/onchain/` contains the `OnChainLogAdapter` scaffold.
- Transparency-log client: `tc_api/transparency/commit_client.py` wraps TruCon communication; shared DSSE predicate/statement construction lives in `tc_api/transparency/dsse_builder.py`.
- TruCon service: `tc_api/trucon/` contains the sequencer, SQLite queue, schemas/auth helpers, and platform adapters.
- Docktap sidecar: `tc_api/docktap/` is the Docker operation interception proxy (sub-package of tc_api). Entry point: `tc-docktap` CLI or `python -m tc_api.docktap.main`.
- Runtime config: `tc_api/config.py` centralizes environment-driven settings (paths, commands, registry, KBS).
- Tests: `tests/` contains pytest modules and manual runners (`test_subprocess_unit.py`, `test_tdx_mr_adapter.py`, `test_api.py`, `test_runner.py`, etc.).
- Scripts: `scripts/` contains operator helpers such as `run_docktap_oob_atomic.py`, `verify_current_attested_head.py`, and `tdvm_smoke_test.py`.
- Docs: `docs/` contains tc_api architecture documentation; trusted-log module docs live in `../tlog/docs/trusted-log/`.

## Conventions
- Prefer extending logic in `tc_api/services/` and keep endpoint handlers in `tc_api/api/routers/` focused on request/response binding.
- Persist per-build artifacts under `builds/<build_id>/`; do not scatter output files in repository root.
- Treat `docker`, `cosign`, `syft`, and `skopeo` as external dependencies; surface clear errors when unavailable.
- Preserve status progression fields (`status`, `current_step`, `error_message`) when changing workflows.
- Keep request/response model changes synchronized with endpoint handlers and tests.
- Agent-facing Docktap preflight should use `POST /api/docktap/authorize` as the primary contract; treat `POST /api/docktap/delegate` as a lower-level operator/debug path rather than the default integration surface.
- The first-version Docktap integration surface intentionally defines one primary preflight contract only; there is no separate status/debug skill contract yet.

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
- Trusted-log module docs: `../tlog/docs/trusted-log/`.

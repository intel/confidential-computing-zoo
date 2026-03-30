# Project Guidelines

## Build and Test
- Setup environment: `bash setup.sh` (creates `venv`, installs `requirements.txt`, initializes directories).
- Start service: `bash start.sh` (recommended; validates tool availability and runs `uvicorn`).
- Alternate start: `python main.py`.
- Run all tests: `bash run_tests.sh`.
- Run manual API checks: `python test_api.py` (or `python test_api.py health|build|publish|register`).
- Run automated tests: `pytest test_unit.py -v`.

## Architecture
- API layer: `main.py` defines FastAPI endpoints and request flow.
- Data contracts: `models.py` contains request/response and status models.
- Service layer: `services.py` encapsulates build/publish/launch workflows and external CLI calls.
- KBS integration: `kbs_service.py` wraps key registration/lookup behavior.
- Transparency logging: `trusted_container_log/tlog_chain.py` provides chained log entry handling.
- Runtime config: `config.py` centralizes environment-driven settings (paths, commands, registry, KBS).

## Conventions
- Prefer extending logic in `services.py` and keep endpoint handlers in `main.py` focused on orchestration.
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
- Test execution details and coverage expectations: `TESTING.md`.

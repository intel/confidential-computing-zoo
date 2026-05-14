# TC API Testing Guide

This document explains how to run the test suite for the TC API service.

## Test Files

- `tests/test_api.py` - Manual integration tests with detailed output
- `tests/test_subprocess_unit.py` - Deterministic subprocess-mocked Docker/non-Docker unit coverage
- `tests/test_tdx_mr_adapter.py` - Focused TDX RTMR adapter unit coverage
- `tests/test_runner.py` - Single test entrypoint for all test types

## Prerequisites

1. Install dependencies:
```bash
pip install -e .
```

2. Start the TC API service (required for manual/integration tests):
```bash
python -m tc_api.api.app
```

The service should be running on `http://localhost:8000`

## Running Tests

Use a single entrypoint for all test flows:

```bash
python -m tests.test_runner --type all
```

### Test types

```bash
python -m tests.test_runner --type manual
python -m tests.test_runner --type unit
```

`--type unit` runs deterministic subprocess-focused coverage in `tests/test_subprocess_unit.py` and RTMR adapter coverage in `tests/test_tdx_mr_adapter.py`.

Useful variants:

```bash
python -m tests.test_runner --type manual --name health
python -m tests.test_runner --type unit --no-service-management
python -m tests.test_runner --type all --verbose
TC_API_BASE_URL=http://localhost:18000 python -m tests.test_runner --type manual --name health
./run_tests.sh --type all --verbose
```

## TD VM Acceptance

Use the smallest supported TDVM flow:

```bash
python -m pytest tests/test_tdx_quote_adapter.py -q
python tests/check_real_tdx_quote.py
./start.sh restart
PYTHONPATH=$PWD/src python scripts/tdvm_smoke_test.py --summary-file /tmp/tdvm-smoke-summary.json
```

Notes:

- `tests/check_real_tdx_quote.py` validates real quote acquisition on the current VM.
- `scripts/tdvm_smoke_test.py` is the supported service-backed smoke runner.
- For shorter runs, use `--skip-deploy` or `--skip-publish`.

## Remote OIDC And Real Rekor Smoke

For remote or SSH environments, prefer the out-of-band token flow:

```bash
PYTHONPATH=$PWD/src python -m tc_api.identity.oidc_preflight --fetch --force-oob
```

Common real-Rekor entrypoints:

```bash
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke --run-real-rekor-oci-multi-chain-smoke
```

If you already have a token, the minimal direct pytest path is:

```bash
TC_API_RUN_REAL_REKOR_TESTS=1 \
TC_API_REAL_REKOR_IDENTITY_TOKEN='<oidc-jwt>' \
python -m pytest tests/test_real_rekor_integration.py -q
```

Short-lived tokens should be treated as just-in-time smoke credentials. Reacquire them instead of trying to reuse stale values.

## Docktap / OpenClaw Validation

Keep the supported OpenClaw validation path narrow:

```bash
./start.sh restart
docker exec -e DOCKER_HOST=unix:///var/run/docktap/docker.sock openclaw-gateway sh -lc 'docker pull hello-world:latest'
PYTHONPATH=$PWD/src ./venv/bin/python scripts/verify_current_attested_head.py docktap-runtime
```

Helpful shortcuts:

- `python scripts/run_docktap_oob_atomic.py` for one-shot OOB login plus Docktap startup and pull replay
- `scripts/verify_current_attested_head.py` for post-pull direct quote-backed verification

If no reusable Sigstore token is cached yet, refresh one first:

```bash
./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
```

## Verification And Mirror Regression

Use exported evidence as the supported operator input:

```bash
tc-verify --evidence evidence.json
tc-verify --evidence evidence.json --json
tc-verify --evidence evidence.json --mirror-dir ./mirror-store --require-mirror
```

Recommended focused verification regression:

```bash
python -m pytest tests/test_tlog_impl.py tests/test_non_tee_verification.py tests/test_verify_cli.py tests/test_oci_bundle_mirror.py -q
```

Real OCI mirror smoke remains opt-in:

```bash
TC_API_RUN_REAL_OCI_MIRROR_TESTS=1 python -m pytest tests/test_real_oci_mirror_integration.py -q
```

## Developing Tests

Current guidance:

1. Add manual API checks to `tests/test_api.py`.
2. Add focused pytest modules next to the closest covered surface.
3. Prefer deterministic subprocess or adapter-level tests before adding new end-to-end flows.
4. Keep long operational walkthroughs in feature-specific docs instead of expanding this file.
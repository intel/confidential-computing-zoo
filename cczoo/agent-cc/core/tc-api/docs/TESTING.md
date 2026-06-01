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

## Result Queries

`build-result`, `publish-result`, `launch-result`, and `luks-result` can be queried directly.

Manual HTTP checks:

```bash
curl http://127.0.0.1:8000/api/build-result/<build_id>
curl http://127.0.0.1:8000/api/publish-result/<build_id>
curl http://127.0.0.1:8000/api/launch-result/<launch_id>
curl http://127.0.0.1:8000/api/luks-result/<user_id>
```

Equivalent CLI checks:

```bash
./venv/bin/tc-client --base-url http://127.0.0.1:8000 build-result <build_id>
./venv/bin/tc-client --base-url http://127.0.0.1:8000 publish-result <build_id>
./venv/bin/tc-client --base-url http://127.0.0.1:8000 launch-result <launch_id>
./venv/bin/tc-client --base-url http://127.0.0.1:8000 luks-result <user_id>
```

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
PYTHONPATH=$PWD python scripts/tdvm_smoke_test.py --summary-file /tmp/tdvm-smoke-summary.json
```

Notes:

- `tests/check_real_tdx_quote.py` validates real quote acquisition on the current VM.
- `scripts/tdvm_smoke_test.py` is the supported service-backed smoke runner.
- For shorter runs, use `--skip-deploy` or `--skip-publish`.

## Remote OIDC And Real Rekor Smoke

For remote or SSH environments, prefer the out-of-band token flow:

```bash
PYTHONPATH=$PWD python -m tc_api.identity.oidc_preflight --fetch --force-oob
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
curl -X POST http://127.0.0.1:8000/api/docktap/authorize \
	-H 'Content-Type: application/json' \
	-d '{"chain_id": "docktap-runtime", "identity_token": "<paste token here>"}'
docker exec -e DOCKER_HOST=unix:///var/run/docktap/docker.sock openclaw-gateway sh -lc 'docker pull hello-world:latest'
PYTHONPATH=$PWD ./venv/bin/python scripts/verify_current_attested_head.py docktap-runtime
```

Helpful shortcuts:

- `python scripts/run_docktap_oob_atomic.py` for one-shot OOB login, authorization preflight, Docktap startup, and pull replay
- `scripts/verify_current_attested_head.py` for post-pull direct quote-backed verification

Docktap now defaults to `DOCKTAP_AUTH_MODE=explicit_delegation`, so the usual operator sequence is: acquire or refresh OIDC, run authorization preflight on `docktap-runtime`, then perform the Docker operation. Use `DOCKTAP_AUTH_MODE=delegation_disabled` only when you intentionally want the stricter per-operation OIDC path.

If no reusable Sigstore token is cached yet, refresh one first:

```bash
./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
```

### Persistent Docktap Success Path

Use this host-side runbook when you want to validate the default explicit-delegation flow without depending on `openclaw-gateway` mounts:

```bash
DOCKTAP_AUTH_MODE=explicit_delegation PYTHONPATH=$PWD \
	./venv/bin/python -m tc_api.docktap.main \
	--socket-path /var/run/docktap/docker.sock \
	--docker-socket-path /var/run/docker.sock
```

In another terminal:

```bash
./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
curl -fsS -X POST http://127.0.0.1:8000/api/docktap/authorize \
	-H 'Content-Type: application/json' \
	-d '{"chain_id":"docktap-runtime", "identity_token":"<paste token here>"}'
DOCKER_HOST=unix:///var/run/docktap/docker.sock docker pull hello-world:latest
PYTHONPATH=$PWD ./venv/bin/python scripts/verify_current_attested_head.py docktap-runtime
```

Expected result:

- `docker pull` returns success through the persistent Docktap socket.
- `verify_current_attested_head.py docktap-runtime` reports `Status: verified`.
- The runtime chain contains baseline, delegation, and pull records, with no residual active intent.

Quick intent check:

```bash
./venv/bin/python - <<'PY'
from tc_api.trucon.database import get_active_commit_intent_for_chain
row = get_active_commit_intent_for_chain('docktap-runtime')
print(dict(row) if row else None)
PY
```

This should print `None` after the successful pull is acknowledged.

### Expired Token Failure Path

Use this regression check to confirm that a background Docktap submission can fail after reservation without leaving an `ACTIVE` intent behind.

Precondition:

- `docktap-runtime` already has a confirmed baseline record. Running the success path once satisfies this.

Start Docktap in the stricter per-operation OIDC mode with an intentionally expired token:

```bash
DOCKTAP_AUTH_MODE=delegation_disabled \
DOCKTAP_SIGSTORE_IDENTITY_TOKEN='<expired-real-sigstore-jwt>' \
PYTHONPATH=$PWD \
	./venv/bin/python -m tc_api.docktap.main \
	--socket-path /var/run/docktap/docker.sock \
	--docker-socket-path /var/run/docker.sock
```

Then run a host-side pull and inspect intent state:

```bash
DOCKER_HOST=unix:///var/run/docktap/docker.sock docker pull busybox:latest
./venv/bin/python - <<'PY'
from tc_api.trucon.database import get_active_commit_intent_for_chain
row = get_active_commit_intent_for_chain('docktap-runtime')
print(dict(row) if row else None)
PY
```

Expected result:

- `docker pull` still completes because Docktap releases the Docker response before the best-effort TruCon background submission finishes.
- Docktap logs show a terminal background failure on the expired token path. In the current Sigstore stack this may surface as `Identity token is malformed or missing claims`.
- `get_active_commit_intent_for_chain('docktap-runtime')` prints `None`.

If you need the SQLite-level proof that the failed runtime reservation was cleaned up, inspect `commit_intents` directly:

```bash
./venv/bin/python - <<'PY'
import sqlite3
from tc_api.trucon.database import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
for row in conn.execute(
    "SELECT intent_token, idempotency_key, status, sequence_num, record_id FROM commit_intents WHERE chain_id = ? ORDER BY created_at ASC",
    ('docktap-runtime',),
):
    print(dict(row))
conn.close()
PY
```

The failed runtime intent should show `status='EXPIRED'`, not `ACTIVE`.

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
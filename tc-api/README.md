# TC API - Trusted Container Build and Publish Service

A RESTful API service framework built with Python and FastAPI for handling Docker image building, packing, launching, deploying of applications runtime in a secure and auditable manner.

## Features

- **Container Image Building**: Build and package container images with Dockerfile and application components
- **SBOM Generation**: Generate and sign SPDX format Software Bill of Materials (SBOM) using Syft
- **Image Security**: Support image encryption using Skopeo and digital signing using Cosign
- **Image Publishing**: Publish signed images and SBOMs to container registries with policy management
- **Key Management**: Integrate with KBS for key management and RVPS for verification policies
- **Secure Deployment**: Support secure container launch with remote attestation in CVM
- **Audit Logging**: Record build and deploy evidence in Transparent Log System
- **Runtime Security**: Enable secure container upgrades during runtime

## Testing

Use the single entrypoint for tests:

```shell
python -m tests.test_runner --type all
```

Common options:

```shell
python -m tests.test_runner --type unit
python -m tests.test_runner --type manual --name health
```

For the opt-in public Rekor smoke test, prefer the just-in-time helper flow so the short-lived OIDC token is fetched and consumed immediately:

```shell
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke
```

In the normal `--fetch` path, the helper now explicitly tries to open a browser for the OIDC login step and falls back to printing the login URL if automatic browser launch is unavailable.

If you already have a real OIDC token and want to enter it interactively instead of exporting it, use:

```shell
python -m tc_api.identity.oidc_preflight --prompt-token --json
```

If you also want to enter the expected signer identity interactively, use:

```shell
python -m tc_api.identity.oidc_preflight --prompt-token --prompt-expected-identity --json
```

For the combined real Rekor + real OCI mirror + real verify multi-chain smoke path, use:

```shell
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke --run-real-rekor-oci-multi-chain-smoke
```

That helper flow opens a browser for Sigstore OIDC login when possible, fetches a fresh short-lived token, enables both real-Rekor and real-OCI opt-in gates, and immediately runs the end-to-end smoke before the token expires.

Current real multi-chain smoke coverage includes:

- real Fulcio-backed DSSE signing using a freshly acquired OIDC token;
- public Rekor upload and lookup;
- real OCI artifact publication to a live local registry through `OciBundleMirror`;
- mirror-backed immutable replay after clearing the adapter's in-process cache;
- `tc-verify --troubleshoot-live --mirror-dir ... --require-mirror` verification of each chain head.

Use `--force-oob` if your environment needs the out-of-band login path.

## Operational Notes

- TruCon is the sole supported trust-event path. The legacy direct trusted-log write path has been retired and is not a valid rollback target.
- Recommended rollout posture is TruCon-only operation with process supervision, parity checks on critical flows, and degraded-mode handling that preserves external business results when trust-event submission is unavailable.
- Docktap keeps only bounded local routing, mapping, and retry state. Replay and verification rely on TruCon and immutable backend state rather than Docktap-local persistence.

## Docktap OIDC

Docktap remains on the same OIDC/Sigstore identity model as the rest of the control plane, but the current operator contract is stricter than before.

- `./start.sh restart` is the local lifecycle entrypoint for `tc_api`, TruCon, and Docktap.
- `start.sh` now enables `DOCKTAP_REQUIRE_ATTESTATION=1` by default.
- If a reusable Sigstore token is already cached, Docktap reuses it automatically.
- If no reusable token is available, Docktap blocks submittable Docker operations such as `pull`, returns an attestation-login challenge, and expects the user to log in and retry the same Docker command.

That means the normal user flow is no longer "always log in before startup". The default flow is "run the stack, try the Docker operation, complete login only if challenged".

Recommended flows:

- Same-machine browser access: keep the default gate enabled, let the Docker command fail with the browser login URL, complete login, then retry.
- Remote SSH session with a browser that can reach the server by IP or hostname: set `DOCKTAP_ATTESTATION_BROWSER_BASE_URL` before `./start.sh restart` so the challenge points at a browser-reachable address instead of remote `localhost`.
- Remote SSH session without callback reachability: use the challenge's out-of-band login command and complete Sigstore verification-code login through `tc-client`.
- Non-interactive process managers: pre-acquire a token with `sigstore-token --format export` and inject `DOCKTAP_SIGSTORE_IDENTITY_TOKEN` into the Docktap process environment.

Examples:

```shell
# Start the local stack with the default attestation gate enabled
./start.sh restart

# If your browser must reach the server on a non-localhost address, override the base URL used in the challenge
DOCKTAP_ATTESTATION_BROWSER_BASE_URL=http://<server-ip>:8000 ./start.sh restart

# Example OpenClaw-side Docker operation through Docktap
docker exec openclaw-gateway sh -lc 'docker pull hello-world:latest'

# Build traffic still flows through Docktap, but current trusted-event submission only covers pull/create/start/stop/rm
docker exec openclaw-gateway sh -lc "mkdir -p /tmp/docktap-build && printf 'FROM hello-world:latest\nLABEL docktap.validation=build\n' >/tmp/docktap-build/Dockerfile && docker build -t docktap-build-probe:latest /tmp/docktap-build"

# Explicit lifecycle validation for run/deploy-style container operations
docker exec openclaw-gateway sh -lc 'docker pull busybox:latest'
docker exec openclaw-gateway sh -lc 'docker create --name docktap-busybox busybox:latest sh -c "sleep 300"'
docker exec openclaw-gateway sh -lc 'docker start docktap-busybox'
docker exec openclaw-gateway sh -lc 'docker stop docktap-busybox'
docker exec openclaw-gateway sh -lc 'docker rm docktap-busybox'

# If challenged, complete remote OOB login with tc-client and retry the same Docker command
tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json

# Atomic helper for OOB login -> Docktap startup -> immediate pull replay -> log capture
python scripts/run_docktap_oob_atomic.py

# Pre-acquire a token for systemd or another non-interactive launcher
python -m tc_api.cli.client \
  --base-url http://127.0.0.1:8000 \
  --sigstore-login oob \
  sigstore-token --format export
```

When the challenge path is triggered, the daemon-style error now looks like this:

```text
Error response from daemon: Attested Docker login required before docker pull.
Browser login: http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap&session_id=<session-id>
Remote login command: tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
If tc-client is unavailable, from the tc_api repo root run: bash setup.sh
Then run: ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
Then retry.
```

`scripts/run_docktap_oob_atomic.py` remains the shortest one-shot debug path when you explicitly want OOB login, Docktap startup, immediate pull replay, and combined log capture in one command.

For manual OpenClaw validation, interpret those commands as follows:

- `docker pull` validates the attestation gate and the `pull` runtime event.
- `docker build` validates that Docker build traffic is still routed through Docktap, but it does not currently emit a TruCon runtime commit.
- `docker create` plus `docker start` is the clearest way to validate `run` or `deploy`-style container activation, because Docktap records `create` and `start` as separate runtime events.
- `docker stop` and `docker rm` validate the shutdown and removal side of the runtime lifecycle.

For the live Docktap -> public Rekor -> TruCon `/commit` debug loop, `scripts/run_docktap_oob_atomic.py` is still the shortest operator path. It discovers the current live `TRUCON_SERVICE_TOKEN`, runs the Sigstore verification-code flow, starts Docktap with that fresh identity token, immediately replays the host and OpenClaw `docker pull` calls, and writes the combined Docktap logs under `logs/`.

## Chain Verification CLI

Operators can verify a trust chain with the package CLI:

```shell
tc-verify default
```

The preferred operator path is to verify from exported attested-head evidence:

```shell
tc-verify --evidence evidence.json
```

Machine-readable output is available with:

```shell
tc-verify default --json
tc-verify --evidence evidence.json --json
```

Useful policy flags:

```shell
tc-verify default --signer-identity alice@example.com
tc-verify default --expected-entry-count 12
tc-verify default --fail-on-pending
tc-verify default --require-tee
tc-verify --evidence evidence.json --mirror-dir ./mirror-store
tc-verify --evidence evidence.json --mirror-dir ./mirror-store --require-mirror
```

Mirror-backed replay verification uses `payload_hash` as the primary lookup anchor for mirrored bundle material. When a mirror is configured, immutable replay can recover predecessor bundles from the mirror if public Rekor entry data does not carry enough payload material on its own.

The current implementation supports both local OCI-layout-style mirrors and registry-backed OCI repositories. The mirror is non-authoritative: Rekor inclusion remains the source of truth, while mirrored bundle material is used to re-materialize verifier-critical DSSE payload fields when public Rekor readback is hash-only.

Current verification tiers are `public-only`, `public+mirrored`, and `public+mirrored+attested`.

Operational notes for mirror-backed replay:

- `TRUCON_BUNDLE_MIRROR_DIR` enables the local OCI-layout-style bundle mirror used by TruCon after Rekor confirmation.
- the same mirror interface also accepts registry-backed repository URLs such as `http://127.0.0.1:5000/tc-api/mirror`;
- mirror publication happens after Rekor confirmation and may lag briefly, so a newly confirmed chain head can remain `public-only` until the mirror publish queue drains;
- `--mirror-dir` points `tc-verify` at a mirror location for payload-hash-based bundle resolution;
- `--require-mirror` upgrades missing mirror material from a best-effort condition to an explicit verification failure or degraded result.

For failure analysis, `tc-verify --json` now emits a top-level `diagnostics` section summarizing immutable replay success, replay provenance, fallback validity, and the first replay entry with a boundary, predecessor, or materialization problem.

Use `chain_id` without `--evidence` only for transitional live fallback verification. In the preferred evidence-backed flow, `tc-verify` derives `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from the exported evidence package, replays immutable-backend history from the attested head, and reports attested-head results separately from fallback diagnostics. Live TruCon verification remains available as fallback and non-TEE fallback remains test-only rather than production-equivalent success.

## Real OCI Mirror Validation

`OciBundleMirror` now supports both local OCI-layout-style storage and real OCI registry repositories. Pass a filesystem path for local storage, or pass a repository URL such as `http://127.0.0.1:5000/tc-api/mirror` for registry-backed storage.

For a real OCI registry smoke test, use:

```shell
TC_API_RUN_REAL_OCI_MIRROR_TESTS=1 python -m pytest tests/test_real_oci_mirror_integration.py -q
```

That test starts a local `registry:2` container, drives `OciBundleMirror.publish_bundle()` and `resolve_bundle()` against the live Registry HTTP API, and verifies round-trip retrieval.

The combined helper above reuses that real registry path while also running the real Rekor multi-chain verification smoke test.

## API Endpoints

### 1. Build and Package
`POST /api/build-package`

Submit container build requests with Dockerfile, application binary, configs, and optional signing/encryption.

***Quick Check***
```shell
curl -X POST "http://localhost:8000/api/build-package" -H "Content-Type:application/json" -d '{"dockerfile":"FROM python:3.9-slim\nWORKDIR .\nCOPY . .","app_binary":"dGVzdCBiaW5hcnkK","configs":["Y29uZmlnCg=="],"data":["ZGF0YQo="],"encrypt":true,"user_id":"test-user"}'
```

**Request Body:**
```json
{
  "dockerfile": "<file>",
  "app_binary": "<file>", // Optional
  "configs": ["file1", "file2"],  // Optional
  "data": ["file3"],  // Optional
  "sign_key": "<private_key.pem>", // Optional
  "cert": "<cert.pem>",  // Optional
  "encrypt": true, 
  "user_id": "test-user"
}
```

**Response:**
```json
{
  "build_id": "bld-xxx",
  "status": "", // build image status
  "estimated_time": "timestamp", 
  "user_id": "user_id",
  "transparencyLog_verify": ""
}
```

### 2. Query Build Result 
`GET /api/build-result/{build_id}`

Query build status and results including image ID, SBOM URL and certificates.

***Quick Check***
```shell
curl  "http://localhost:8000/api/build-result/{build_id}"
```

**Response:**
```json
{
  "user_id":"test-user",
  "build_id":"{build_id}",
  "status":"success",
  "current_step":"Build completed successfully",
  "image_id":"oci:./builds/{build_id}/test-{build_id}",
  "sbom_url":"./builds/{build_id}/user-{build_id}-sbom.json",
  "image_url":"./builds/{build_id}/user-{build_id}",
  "cert_url":"/api/artifacts/{build_id}/cosign.crt",
  "log_id":"xxxxxxx",
  "transparencyLog_verify":"success",
  "error_message":null,
  "created_at":"<timestamp>",
  "updated_at":"<timestamp>"
}
```

### 3. Publish Package
`POST /api/publish-package`

Publish built image and SBOM with key management and evidence logging.

***Quick Check***
```shell
curl  curl -X POST "http://localhost:8000/api/publish-package" -H "Content-Type:application/json" -d '{"build_id":"{build_id}","image_id":"{image_id}","user_id":"{user_id}","sbom_url":"{sbom_url}","log_evidence":true}'
```

**Request:**
```json

  {
    "build_id":"{build_id}",
    "status":"success",
    "image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted", // Optional
    "user_id":"{user_id}",
    "image_id":"test-{build_id}",
    "sbom_url":"./builds/{build_id}/{build_id}-sbom.json",
    "log_evidence":"True"
  }
```

**Response:**
```json
  {
    "build_id":"{build_id}",
    "status":"success",
    "image_url":"docker.io/trustedzoo/test-{build_id}:latest-encrypted",
    "user_id":"test-user",
    "image_id":"test-{build_id}",
    "sbom_url":"./builds/{build_id}/{build_id}-sbom.json",
    "log_id":"xxxxxxxxx",
    "transparencyLog_verify":"success",
    "published_at":"<timestamp>"
  }
```

### 4. Query Publish Result
`GET /api/publish-result/{build_id}`

Query publish status and results including image ID, SBOM URL ...

***Quick Check***
```shell
curl  "http://localhost:8000/api/publish-result/{build_id}"
```

**Response:**
```json
{
  "user_id":"test-user",
  "build_id":"{build_id}",
  "status":"success",
  "current_step":"Build completed successfully",
  "image_id":"oci:./builds/{build_id}/user-{build_id}",
  "sbom_url":"./builds/{build_id}/user-{build_id}-sbom.json",
  "image_url":"./builds/{build_id}/user-{build_id}",
  "cert_url":"/api/artifacts/{build_id}/cosign.crt",
  "log_id":"xxxxxxx",
  "transparencyLog_verify":"success",
  "error_message":null,
  "created_at":"<timestamp>",
  "updated_at":"<timestamp>"
}
```


### 5. Deploy Launch
`POST /api/deploy-launch`

Launch container with attestation and secure deployment.

***Quick Check***
```shell
curl -X POST "http://localhost:8000/api/deploy-launch" -H "Content-Type:application/json" -d '{"image_id":"test-{build_id}","build_id": "{build_id}","user_id":"test-user","image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted","sbom_url":null,"attestation_required":true}'
```

**Request:**
```json
{
  "image_id":"test-{build_id}",
  "build_id": "{build_id}",
  "user_id":"test-user",
  "image_url":"docker.io/{docker_account}/test-{build_id}:latest-encrypted", // Optional
  "sbom_url":null,  // Optional
  "attestation_required":true
}
```

**Response:**
```json
{
  "launch_id":"launch-xxxxxxx",
  "status":"initiated",
  "user_id":"test-user",
  "log_id":null,
  "transparencyLog_verify":null,
  "created_at":"<timestamp>"
}
```

### 6. Query Launch Result
`GET /api/launch-result/{launch_id}`

Query launch status and attestation results.

***Quick Check***
```shell
curl "http://localhost:8000/api/launch-result/{launch_id}"

```
**Response:**
```json
{
  "launch_id": "launch-######",           
  "status": "success",                     
  "validation": "passed",                  
  "attestation": "trusted",             
  "log_id": "tx-xxxxxxx",              
  "instance_id": [                        
    "inst-#####1",
    "inst-#####2"
  ]
}
```

### 7. Query transparency log
`GET /api/transparency-log/{log_id}`

Query transparency status including transparency log content, build_id and log_id.

***Quick Check***
```shell
curl  "http://localhost:8000/api/transparency-log/{log_id}"

```
**Response:**
```json
  {
    "user_id":"test-user",
    "build_id":"bld-xxxxxx",
    "log_id":"xxxxxxxxx",
    "status":"added",
    "transparency_log":"<log content>",
    "transparencyLog_verify":null,
    "error_message":null
  }
```

### 8. Query all taransparency log
`POST /api/get-summaryTransparencylog`

Query all transparency log.

***Quick Check***
```shell
curl "http://localhost:8000/api/get-summaryTransparencylog" -H "Content-Type:application/json" -d '{"build_id":"{build_id}","launch_id":"{launch_id}"}'

```
**Response:**
```json
{
  "build_id":"{build_id}",
  "launch_id":"{launch_id}",
  "log_id":{
    "build":"xxxxxxxxx",
    "publish":"xxxxxxxxx",
    "launch":"xxxxxxxxx"
    },
  "transparencylog":{
    "build":"<build transparency log coentent>",
    "publish":"<publish transparency log coentent>",
    "launch":"<launch transparency log coentent>"
  }
}
```

## Quick Start

### Set Up Environment

Before running the tests, make sure you have configured your Docker Hub (`docker.io`) account.  
Otherwise, tests involving image build, push, and deployment will fail.

#### Configure docker.io account
1. Log in using the CLI:

```bash
   docker login docker.io
```
or
```bash
   skopeo login docker.io
```
Enter your Docker Hub username and password (or Personal Access Token).

2. Verify login:

```bash
   docker info
```
This should show your username under "Username" and confirm you are logged in.

3. For CI/CD environments, you can pass credentials via environment variables:

```bash
export DOCKER_USERNAME=<your-username>
export DOCKER_PASSWORD=<your-password-or-token>
echo "$DOCKER_PASSWORD" | docker login -u "$DOCKER_USERNAME" --password-stdin docker.io
```
Please note, you need to update DOCKER_REPOSITORY in `config.py` to your Docker Hub repository name before running the tests.

### Install Dependencies and use python virtual env(python is already installed)

1. Create & active virtual environment

```bash
python -m venv {env-name}
source {env-name}/bin/activate
```

2. Install dependencies

```bash
cd tc_api
pip install -e .
```

3. Start ASR && AA && CDH && KBS

Please refer to: [https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file](https://github.com/RodgerZhu/deploy-encrypted-image-in-tdvm?tab=readme-ov-file).

### Unified Local Startup

If you want one local entrypoint without merging trust-stack logic into `start.sh`, use `scripts/dev-up.sh`.

What it does:

- Verifies that KBS is reachable on `KBS_HOST:KBS_PORT` (defaults: `127.0.0.1:8080`)
- Builds the trust-service image from `aa_asr_cdh/Dockerfile` if needed
- Starts the AA/CDH/ASR trust-service container on the host network
- Hands off to the existing `./start.sh` for `tc_api + trucon + docktap`

What it does not do:

- It does not start KBS for you. KBS remains an external dependency.
- It does not move AA/CDH/ASR into the main `start.sh`; the trust stack stays separately managed.

Example:

```bash
# Ensure KBS is already running on localhost:8080
bash scripts/dev-up.sh
```

If the external trust-service / KBS side is already prepared separately, use `./start.sh restart` directly for the local `tc_api + trucon + docktap` lifecycle.

Useful environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `KBS_HOST` | `127.0.0.1` | Host checked before trust-service startup |
| `KBS_PORT` | `8080` | Port checked before trust-service startup |
| `TRUST_SERVICE_IMAGE` | `tc-api-trust-service:dev` | Image tag used for the AA/CDH/ASR container |
| `TRUST_SERVICE_CONTAINER_NAME` | `tc-api-trust-service` | Container name used by the wrapper |
| `TRUST_SERVICE_BUILD` | `missing` | `missing`, `always`, or `never` |
| `TRUST_SERVICE_PORT` | `8006` | Port used to confirm `api-server-rest` readiness |

When `scripts/dev-up.sh` exits, it stops the trust-service container it started. The underlying `start.sh` cleanup still owns `trucon` and `docktap`.

Under `start.sh`, the default runtime log files are:

- `logs/docktap-latest.log` for Docktap proxy activity and `initial_bundle_rekor_*` acceptance logs
- `logs/trucon-latest.log` for TruCon queueing, retries, and `confirmed_rekor_*` confirmation logs

### Run Service

The supported local entrypoint is:

```bash
./start.sh restart
```

For development or direct API-only work, you can still run:

```bash
python -m tc_api.api.app
```

### TD VM Acceptance

Use the smallest supported acceptance flow on a real TD VM:

```bash
PYTHONPATH=$PWD/src python tests/check_real_tdx_quote.py
./start.sh restart
PYTHONPATH=$PWD/src python scripts/tdvm_smoke_test.py --summary-file /tmp/tdvm-smoke-summary.json
```

Notes:

- `tests/check_real_tdx_quote.py` verifies real quote acquisition on the current VM.
- `scripts/tdvm_smoke_test.py` is the supported smoke runner for service-backed TDVM validation.
- For a shorter run, add `--skip-publish` or `--skip-deploy` to `scripts/tdvm_smoke_test.py`.
- More detailed TDVM guidance lives in `docs/TESTING.md`.

### Containers

Current supported container entrypoints are:

```bash
docker compose up -d
```

or, for single-host development that also manages the trust-service wrapper:

```bash
../scripts/dev-up.sh
```

Docker Compose brings up `tc-api`, `trucon`, and `docktap`. Detailed environment and health-check guidance belongs in `docs/architecture.md` and `docs/TESTING.md` rather than this README.

### Docktap Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TRUCON_URL` | `http://127.0.0.1:8001` | TruCon endpoint for event submission |
| `TRUCON_UDS_PATH` | `/var/run/trucon/trucon.sock` | Preferred same-machine Unix socket path for tc_api and Docktap internal TruCon traffic |
| `TRUCON_SERVICE_TOKEN` | (generated) | Shared Bearer token for TruCon auth |
| `SOCK_BRIDGE_SOCKET` | `/tmp/docker-proxy.sock` | Proxy socket listen path |
| `DOCKER_SOCKET` | `/var/run/docker.sock` | Docker daemon socket path |
| `DOCKTAP_HEALTH_PORT` | `8002` | HTTP health endpoint port |
| `DOCKTAP_SOCKET` | `/var/run/docktap/docker.sock` | Proxy socket path (bare-metal `start.sh`) |
| `DOCKTAP_REQUIRE_ATTESTATION` | `1` | Block submittable Docker operations until a reusable Sigstore token is available |
| `DOCKTAP_ATTESTATION_API_URL` | `http://127.0.0.1:8000` | Base API URL embedded in the attestation-login challenge |
| `DOCKTAP_ATTESTATION_BROWSER_BASE_URL` | `http://127.0.0.1:8000` | Browser-visible base URL embedded in the attestation-login challenge |
| `DOCKTAP_LOG_FILE` | `./logs/docktap-latest.log` | Docktap runtime log path used by `start.sh` |
| `TRUCON_LOG_FILE` | `./logs/trucon-latest.log` | TruCon runtime log path used by `start.sh` |

## Configuration

Configure via environment variables:

- `HOST`: Service listening address (default: 0.0.0.0)
- `PORT`: Service port (default: 8000)
- `DOCKER_REGISTRY`: Docker image registry address
- `ENABLE_TDX`: enable TDX-specific flow and mounts (`true` or `false`, default `false`)
- `UPLOAD_DIR`: File upload directory
- `BUILD_DIR`: Build working directory

## Dependencies

The service depends on the following external tools, please ensure they are properly installed:

- Docker
- Cosign
- Syft  
- Skopeo
- KBS Client (optional)

## Project Structure

```
tc-api/
├── src/
│   └── tc_api/                  # Application package
│       ├── main.py              # FastAPI application entry and API routes
│       ├── services.py          # Build/publish/launch workflow logic
│       ├── models.py            # Pydantic request/response models
│       ├── config.py            # Environment-driven runtime settings
│       ├── kbs_service.py       # KBS integration helpers
│       ├── tlog_client.py       # Trusted-log client and verification helpers
│       ├── docktap/             # Docker interception sidecar package
│       ├── trucon/              # TruCon sequencer service package
│       └── cli/                 # CLI entrypoints such as tc-client and tc-verify
├── tests/                       # Focused pytest modules and manual checks
├── scripts/                     # Operator helpers such as tdvm_smoke_test.py
├── docs/                        # Architecture and testing docs
├── pyproject.toml               # Packaging and entrypoints
├── setup.sh                     # Local development environment setup
├── start.sh                     # Local service orchestration
└── run_tests.sh                 # Backward-compatible test wrapper
```

## Testing

Use the single entrypoint for everyday testing:

```bash
python -m tests.test_runner --type all
```

Useful current variants:

```bash
python -m tests.test_runner --type unit
python -m tests.test_runner --type manual --name health
python -m tests.test_runner --type manual --base-url http://localhost:18000 --manual-ready-timeout 90
./run_tests.sh --type all --verbose
```

Current focused automated slices are:

- `tests/test_subprocess_unit.py`
- `tests/test_tdx_mr_adapter.py`

Manual API checks live in `tests/test_api.py`.

See `docs/TESTING.md` for the full matrix and `docs/architecture.md` for system design.

Docktap-specific design details are in `docs/docktap/architecture.md`.

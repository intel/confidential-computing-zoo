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

## Quick Start

### Prerequisites

- TDX guest support is mandatory. The runtime expects `/dev/tdx_guest`, RTMR extend support, and quote generation to be available.
- Docker, Cosign, Syft, and Skopeo must be installed.
- KBS / trust-service dependencies must be reachable for full build and launch flows.

### Local Startup

The supported local lifecycle entrypoint is:

```bash
./start.sh restart
```

To stop services without starting them again:

```bash
./start.sh stop
```

To restart and clear local TruCon / Docktap runtime state first:

```bash
./start.sh restart --reset-state
```

To clear local state without starting services:

```bash
./start.sh reset-state
```

`--reset-state` and `reset-state` remove the local TruCon queue database, derived chain state stored in that database, SQLite WAL/SHM files, the TruCon lock file, and the Docktap workload database. They are the supported way to recover from stale local chain or queue state during development.

They do not remove build artifacts under `builds/`, published mirror material, or the cached Sigstore identity token file.

If you want a wrapper that also manages the local AA / CDH / ASR trust-service container, use:

```bash
bash scripts/dev-up.sh
```

For direct API-only development you can still run:

```bash
python -m tc_api.api.app
```

### TDVM Smoke Path

Use the smallest supported acceptance flow on a real TD VM:

```bash
PYTHONPATH=$PWD/src python tests/check_real_tdx_quote.py
./start.sh restart
PYTHONPATH=$PWD/src python scripts/tdvm_smoke_test.py --summary-file /tmp/tdvm-smoke-summary.json
```

For a shorter run, add `--skip-publish` or `--skip-deploy` to `scripts/tdvm_smoke_test.py`.

## Configuration

Primary runtime configuration comes from environment variables:

- `HOST`: service listen address, default `0.0.0.0`
- `PORT`: service port, default `8000`
- `DOCKER_REGISTRY`: image registry address
- `UPLOAD_DIR`: upload directory
- `BUILD_DIR`: build working directory
- `TRUCON_UDS_PATH`: preferred same-machine Unix socket path for internal TruCon traffic
- `TRUCON_SERVICE_TOKEN`: shared Bearer token for tc_api and Docktap
- `TRUCON_BUNDLE_MIRROR_DIR`: optional local OCI-layout bundle mirror

Docktap-specific variables are listed later in this README.

## Project Structure

```text
tc-api/
├── src/tc_api/          # tc_api, TruCon, Docktap, CLI, and shared models
├── tests/               # focused pytest modules and manual checks
├── scripts/             # operator helpers such as tdvm_smoke_test.py
├── docs/                # architecture and testing docs
├── pyproject.toml       # packaging and entrypoints
├── setup.sh             # local environment setup
├── start.sh             # local service orchestration
└── run_tests.sh         # backward-compatible test wrapper
```

## Testing

Use the single entrypoint for everyday testing:

```bash
python -m tests.test_runner --type all
```

Common variants:

```bash
python -m tests.test_runner --type unit
python -m tests.test_runner --type manual --name health
python -m tests.test_runner --type manual --base-url http://localhost:18000 --manual-ready-timeout 90
./run_tests.sh --type all --verbose
```

Opt-in real-signing and public-Rekor flows:

```bash
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke
python -m tc_api.identity.oidc_preflight --fetch --run-real-rekor-smoke --run-real-rekor-oci-multi-chain-smoke
python -m tc_api.identity.oidc_preflight --prompt-token --json
```

Useful focused slices:

- `tests/test_subprocess_unit.py`
- `tests/test_tdx_mr_adapter.py`
- `tests/test_real_oci_mirror_integration.py` with `TC_API_RUN_REAL_OCI_MIRROR_TESTS=1`

See `docs/TESTING.md` for the full matrix.

## Operational Notes

- TruCon is the sole supported trust-event path. The legacy direct trusted-log write path has been retired and is not a valid rollback target.
- Recommended rollout posture is TruCon-only operation with process supervision, parity checks on critical flows, and degraded-mode handling that preserves external business results when trust-event submission is unavailable.
- Docktap keeps only bounded local routing, mapping, and retry state. Replay and verification rely on TruCon and immutable backend state rather than Docktap-local persistence.

## Docktap OIDC

Docktap uses the same OIDC / Sigstore identity model as the rest of the control plane.

Current operator contract:

- `./start.sh restart` starts `tc_api`, TruCon, and Docktap together.
- `DOCKTAP_REQUIRE_ATTESTATION=1` is enabled by default.
- If a reusable Sigstore token is cached, Docktap reuses it.
- If no reusable token is available, submittable Docker operations such as `pull` are blocked until the user completes the attestation-login challenge.

Recommended flows:

- Same-machine browser access: retry the Docker command after completing the browser login challenge.
- Remote SSH with browser reachability: set `DOCKTAP_ATTESTATION_BROWSER_BASE_URL` before startup.
- Remote SSH without callback reachability: use the out-of-band `tc-client` login command from the challenge.
- Non-interactive launchers: pre-acquire a token and inject `DOCKTAP_SIGSTORE_IDENTITY_TOKEN`.

Example OOB flow:

```shell
./start.sh restart
docker exec openclaw-gateway sh -lc 'docker pull hello-world:latest'
tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
python scripts/run_docktap_oob_atomic.py
```

Example challenge error:

```text
Error response from daemon: Attested Docker login required before docker pull.
Browser login: http://127.0.0.1:8000/api/sigstore/interactive-login?operation=docktap&session_id=<session-id>
Remote login command: tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
If tc-client is unavailable, from the tc_api repo root run: bash setup.sh
Then run: ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
Then retry.
```

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

Use `chain_id` without `--evidence` only for transitional live fallback verification. In the preferred evidence-backed flow, `tc-verify` derives `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from the exported evidence package, replays immutable-backend history from the attested head, and reports attested-head results separately from fallback diagnostics. Live TruCon verification remains available for troubleshooting, but production verification is expected to run against exported attested-head evidence on TDX-backed chains.

## Real OCI Mirror Validation

`OciBundleMirror` now supports both local OCI-layout-style storage and real OCI registry repositories. Pass a filesystem path for local storage, or pass a repository URL such as `http://127.0.0.1:5000/tc-api/mirror` for registry-backed storage.

For a real OCI registry smoke test, use:

```shell
TC_API_RUN_REAL_OCI_MIRROR_TESTS=1 python -m pytest tests/test_real_oci_mirror_integration.py -q
```

That test starts a local `registry:2` container, drives `OciBundleMirror.publish_bundle()` and `resolve_bundle()` against the live Registry HTTP API, and verifies round-trip retrieval.

The combined helper above reuses that real registry path while also running the real Rekor multi-chain verification smoke test.

## API Summary

Common API surfaces:

| Area | Endpoint |
|---|---|
| Build | `POST /api/build-package`, `GET /api/build-result/{build_id}` |
| Publish | `POST /api/publish-package`, `GET /api/publish-result/{build_id}` |
| Launch | `POST /api/deploy-launch`, `GET /api/launch-result/{launch_id}` |
| Transparency | `GET /api/transparency-log/{log_id}`, `POST /api/get-summaryTransparencylog` |

For local manual checks, run the service and use the built-in FastAPI docs or the manual tests in `tests/test_api.py`.

## Docktap Environment Variables

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

## Further Reading

- `docs/TESTING.md` for the full test matrix
- `docs/architecture.md` for deployment and control-plane architecture
- `docs/trusted-log/README.md` for TruCon and chain semantics
- `docs/docktap/architecture.md` for Docktap-specific design details

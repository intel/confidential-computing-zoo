# TC API Testing Guide

This document explains how to run the test suite for the TC API service.

## Test Files

- `tests/test_api.py` - Manual integration tests with detailed output
- `tests/test_unit.py` - Automated unit and integration tests using pytest
- `tests/test_subprocess_unit.py` - Deterministic subprocess-mocked Docker/non-Docker unit coverage
- `tests/test_runner.py` - Single test entrypoint for all test types

## Prerequisites

1. Install dependencies:
```bash
pip install -e .
```

2. Start the TC API service (required for manual/integration tests):
```bash
python -m tc_api.main
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
python -m tests.test_runner --type integration
python -m tests.test_runner --type performance
```

`--type unit` runs deterministic subprocess-focused coverage in `tests/test_subprocess_unit.py`.

### Useful options

```bash
python -m tests.test_runner --type manual --name health
python -m tests.test_runner --type all --verbose
python -m tests.test_runner --type all --stop-on-fail
python -m tests.test_runner --type unit --no-service-management
python -m tests.test_runner --type manual --name health --base-url http://localhost:18000 --manual-ready-timeout 90
```

Manual tests can target a non-default endpoint:

```bash
TC_API_BASE_URL=http://localhost:18000 python -m tests.test_runner --type manual --name health
```

Backward-compatible wrappers still work:

```bash
bash run_tests.sh --type all
```

## TD VM Acceptance

For a real Intel TDX TD VM, treat quote acquisition and end-to-end smoke as separate acceptance gates.

Recommended order:

```bash
python -m pytest tests/test_tdx_quote_adapter.py -q
python tests/check_real_tdx_quote.py
bash start.sh
PYTHONPATH=$PWD/src python tdvm_smoke_test.py --summary-file /tmp/tdvm-smoke-summary.json
```

What each step validates:

- `tests/test_tdx_quote_adapter.py` keeps adapter-level fallback behavior deterministic.
- `tests/check_real_tdx_quote.py` validates real quote acquisition on the current VM and compares the repository adapter against a direct `libtdx_attest` probe.
- `tdvm_smoke_test.py` validates service readiness, build, SBOM, encryption, and optionally publish / deploy.

### Real TDX Quote Path on Current TD VM

The current repository implementation supports two quote paths:

- configfs / TSM path via `/sys/kernel/config/tsm/report/reportdata` and `/sys/kernel/config/tsm/report/outblob`;
- `libtdx_attest` fallback for TD VMs where configfs quote interfaces are absent.

On the current real TD VM, the observed working path is the `libtdx_attest` flow rather than configfs. Practical indicators were:

- `/sys/kernel/config/tsm/report/reportdata` and `/sys/kernel/config/tsm/report/outblob` do not exist;
- `/dev/tdx_guest` and `/etc/tdx-attest.conf` are present;
- direct probing through `libtdx_attest.so` succeeds and matches the repository adapter output.

This is why `src/tc_api/trucon/adapters/tdx_quote.py` now falls back to `libtdx_attest` when configfs quote files are unavailable.

### TD VM Smoke Behavior

`tdvm_smoke_test.py` is the standard smoke entrypoint for a real TD VM.

Important current behavior:

- it can run the repository-backed real quote check before touching the API service;
- it uses stdlib HTTP only, so it does not depend on `requests` being installed;
- it auto-skips `publish` and `deploy` when `DOCKER_REPOSITORY` is unset or still contains the placeholder value;
- it writes a machine-readable summary file when `--summary-file` is provided.

### Non-TDX Deploy Smoke Constraints

The current service stack used in this repository can run with `ENABLE_TDX=false`. On that path, real quote acquisition on the VM can still succeed, but deploy smoke must not assume TDX-specific launch decryption is available inside the service.

The validated behavior from the current real smoke is:

- `tdvm_smoke_test.py` auto-forces non-encrypted deploy smoke when the service configuration reports `ENABLE_TDX=false`;
- launch skips TDX attestation device mounts and skips SBOM signature verification when no `cosignPub` key is available from the launch key material;
- build and publish can still complete with real Sigstore/OIDC-backed transparency verification in this mode.

Operationally, this means that on the current VM and local service stack, the correct full smoke target is:

- real quote acquisition;
- baseline immutable replay;
- non-encrypted build;
- non-encrypted publish to the local registry;
- non-TDX launch.

Do not treat non-encrypted deploy smoke on this stack as a regression. It is the expected acceptance path until the service itself is running with TDX-enabled launch/decryption support.

For build-only validation on a TD VM without registry setup:

```bash
PYTHONPATH=$PWD/src python tdvm_smoke_test.py --skip-deploy --summary-file /tmp/tdvm-smoke-summary.json
```

### Local Registry Publish Smoke

When validating publish without relying on an external registry, a local `registry:2` container is enough:

```bash
docker rm -f tc-api-local-registry >/dev/null 2>&1 || true
docker run -d --name tc-api-local-registry -p 5000:5000 registry:2
export DOCKER_REPOSITORY=localhost:5000/tcapi
```

The current service implementation treats `localhost` / `127.0.0.1` registry targets as insecure local registries and uses `skopeo copy --dest-tls-verify=false` for that path. This is only intended for local smoke validation.

### Launch Import Path Used by Real Smoke

The current deploy smoke no longer relies on `skopeo copy ... docker-daemon:...` during launch.

That transport proved unreliable in the current environment for two separate reasons during validation:

- Docker API version negotiation via `docker-daemon:` was too old for publish/import on this daemon in some paths;
- direct OCI-to-`docker-daemon:` import in launch could fail even after the image had been pulled successfully.

The stable launch path now validated by the real smoke is:

```bash
skopeo copy oci:<launch-dir>/encrypted docker-archive:<launch-dir>/<image>-image.tar:<image>:latest
docker load -i <launch-dir>/<image>-image.tar
docker run ... <image>:latest
```

This is the path to preserve when debugging or refactoring launch on the current stack. It is the reason the end-to-end real smoke now reaches a running container in non-TDX mode.

### Recommended Full Real Smoke Command

For the currently validated local-registry and remote-OIDC setup, use one chained command so the short-lived Sigstore token stays valid through the whole smoke:

```bash
export DOCKER_REPOSITORY=localhost:5000/tcapi
export PYTHONPATH=$PWD/src
export TC_API_REAL_REKOR_IDENTITY_TOKEN_MIN_TTL=0

python -m tc_api.oidc_preflight --fetch --force-oob && \
python tdvm_smoke_test.py --summary-file /tmp/tdvm_smoke_full_deploy_summary.json
```

On the current validated run, that sequence completed all of the following successfully:

- build with `transparencyLog_verify = success`;
- publish with `transparencyLog_verify = success`;
- baseline immutable replay with explicit CCEL size / decode audit fields;
- deploy-launch with a running container result.

## Sigstore OIDC in Remote / SSH Environments

Short-lived Sigstore OIDC tokens from `https://oauth2.sigstore.dev/auth` typically expire in about 60 seconds. The current implementation reduces repeated browser logins by caching and reusing still-valid tokens.

Relevant environment variables:

```bash
TC_API_REAL_REKOR_IDENTITY_TOKEN
TC_API_REAL_REKOR_IDENTITY_TOKEN_CACHE
TC_API_REAL_REKOR_IDENTITY_TOKEN_MIN_TTL
TC_API_SIGSTORE_INTERACTIVE_LOGIN
```

Current behavior:

- the service first checks `TC_API_REAL_REKOR_IDENTITY_TOKEN`;
- then it checks in-process memory and the on-disk cache, defaulting to `/dev/shm/tc_api_sigstore_identity_token.json`;
- it parses the JWT `exp` claim and only reuses tokens whose remaining lifetime is above the configured minimum TTL;
- only when no reusable token exists does it fall back to interactive acquisition, and only if `TC_API_SIGSTORE_INTERACTIVE_LOGIN=true`.

For SSH or other remote environments, prefer the out-of-band login path instead of the local callback flow:

```bash
PYTHONPATH=$PWD/src python -m tc_api.oidc_preflight --fetch --force-oob
```

That flow prints a browser URL and a one-time verification-code prompt, which avoids the common problem where remote `localhost:<port>` callback URLs cannot be opened reliably from the user's local browser.

### One-Login Build / Publish Validation

The following sequence was validated successfully on the current environment:

```bash
docker rm -f tc-api-local-registry >/dev/null 2>&1 || true
docker run -d --name tc-api-local-registry -p 5000:5000 registry:2

export DOCKER_REPOSITORY=localhost:5000/tcapi
export TC_API_SIGSTORE_INTERACTIVE_LOGIN=false
export TC_API_REAL_REKOR_IDENTITY_TOKEN_MIN_TTL=0

bash start.sh
PYTHONPATH=$PWD/src python -m tc_api.oidc_preflight --fetch --force-oob
PYTHONPATH=$PWD/src python tdvm_smoke_test.py --skip-preflight --skip-quote-check --skip-deploy --summary-file /tmp/tdvm-token-reuse-smoke.json
```

This verified the intended operational property: one OIDC login was sufficient for the subsequent build and publish flow, with no second browser login prompt during the service-side Sigstore operations.

## Verification CLI Checks

The operator-facing chain verification CLI can be exercised directly:

```bash
tc-verify --evidence evidence.json
tc-verify --evidence evidence.json --json
tc-verify default
tc-verify default --json
tc-verify default --signer-identity alice@example.com
tc-verify default --expected-entry-count 12
tc-verify default --fail-on-pending
tc-verify default --require-tee
tc-verify --evidence evidence.json --mirror-dir ./mirror-store
tc-verify --evidence evidence.json --mirror-dir ./mirror-store --require-mirror
```

Mirror-backed verification notes:

- set `TRUCON_BUNDLE_MIRROR_DIR=/path/to/mirror-store` when exercising TruCon post-confirmation mirror publication locally;
- use `--mirror-dir` to point `tc-verify` at the mirrored bundle store;
- use `--require-mirror` to turn missing mirrored bundle material into an explicit failure or degraded verification result instead of a best-effort `public-only` replay run;
- a short-lived `public-only` window is expected immediately after Rekor confirmation and before the asynchronous mirror publish queue drains.

Recommended targeted regression for the verification plane:

```bash
python -m pytest tests/test_tlog_impl.py tests/test_non_tee_verification.py tests/test_verify_cli.py tests/test_oci_bundle_mirror.py -q
```

## Real OCI Mirror Smoke Test

`OciBundleMirror` supports both local OCI-layout-style storage and real registry-backed repositories. To exercise a real OCI artifact round-trip against an actual registry API, use the opt-in smoke test below.

Prerequisites:

- local Docker daemon available to the test process;
- ability to pull and run `registry:2`, or set `TC_API_REAL_OCI_REGISTRY_IMAGE` to an equivalent registry image.

Run:

```bash
TC_API_RUN_REAL_OCI_MIRROR_TESTS=1 \
python -m pytest tests/test_real_oci_mirror_integration.py -q
```

Optional environment variables:

```bash
TC_API_REAL_OCI_REGISTRY_IMAGE=registry:2
TC_API_REAL_OCI_MIRROR_REPOSITORY=tc-api/oci-bundle-mirror-smoke
```

This smoke test starts a real local registry container, runs `OciBundleMirror.publish_bundle()` and `resolve_bundle()` against that live registry, and verifies bundle and annotation integrity.

## Public Rekor Smoke Test

An opt-in smoke test is available for validating tc_api's real Sigstore signing path against a public Rekor service:

```bash
TC_API_RUN_REAL_REKOR_TESTS=1 \
TC_API_REAL_REKOR_IDENTITY_TOKEN='<oidc-jwt>' \
python -m pytest tests/test_real_rekor_integration.py -q
```

Optional environment variables:

```bash
TC_API_REAL_REKOR_URL=https://rekor.sigstore.dev
TC_API_REAL_REKOR_SIGNER_IDENTITY=alice@example.com
```

Before running the public Rekor smoke test, you can preflight-check the OIDC token locally without printing the raw token:

```bash
python -m tc_api.oidc_preflight --json
```

If you already have a real OIDC token and prefer an interactive prompt instead of exporting an environment variable, use:

```bash
python -m tc_api.oidc_preflight --prompt-token --json
```

If you also want to enter the expected signer identity interactively, use:

```bash
python -m tc_api.oidc_preflight --prompt-token --prompt-expected-identity --json
```

To reduce friction from the short token lifetime, you can also let the helper fetch a fresh token on demand and immediately run the smoke test in the same process:

```bash
python -m tc_api.oidc_preflight --fetch --run-real-rekor-smoke
```

In the normal `--fetch` flow, the helper now explicitly tries to open a browser for the OIDC login step. If automatic browser launch fails, it prints the login URL so you can open it manually and continue the same flow.

For the combined real Rekor + real OCI mirror + real verify multi-chain smoke path, use:

```bash
python -m tc_api.oidc_preflight --fetch --run-real-rekor-smoke --run-real-rekor-oci-multi-chain-smoke
```

That helper enables both the real Rekor and real OCI mirror opt-in gates, fetches a fresh token via browser-assisted OIDC login, then runs the multi-chain smoke node that publishes mirrored bundles to a live local OCI registry and verifies each chain through the `tc-verify` troubleshooting path with `--require-mirror`.

The current real multi-chain smoke validates all of the following in one run:

- real Sigstore signing with a freshly acquired token;
- public Rekor persistence and replay;
- registry-backed OCI artifact publication and resolution through `OciBundleMirror`;
- mirror-backed replay after clearing the adapter's in-process bundle cache;
- live troubleshooting verification output from `tc-verify` with `verification_tier=public+mirrored`.

If your environment needs the out-of-band flow, use:

```bash
python -m tc_api.oidc_preflight --fetch --force-oob --run-real-rekor-smoke
```

You can still pass extra pytest selectors through the helper when narrowing the smoke run:

```bash
python -m tc_api.oidc_preflight --fetch --run-real-rekor-smoke --pytest-args -q -k multi_chain
```

Or read the token from stdin instead of an environment variable:

```bash
printf '%s' "$TC_API_REAL_REKOR_IDENTITY_TOKEN" | python -m tc_api.oidc_preflight --stdin --json
```

The preflight check validates the basic Sigstore expectations that commonly cause failures before Fulcio issuance:

- required JWT claims exist (`iss`, `aud`, `sub`, `iat`, `exp`)
- `aud` includes `sigstore`
- the token is still within its validity window
- tokens that are already expired are rejected before pytest starts
- tokens that are about to expire trigger a warning so the smoke run can be retried with a fresh fetch
- the signer identity that sigstore-python will derive matches `TC_API_REAL_REKOR_SIGNER_IDENTITY` when provided

For common issuers, the derived signer identity follows sigstore-python's built-in rules:

- `https://token.actions.githubusercontent.com` → uses `sub`
- `https://accounts.google.com` → uses `email`
- `https://oauth2.sigstore.dev/auth` → uses `email`

Notes:

- The test is skipped unless `TC_API_RUN_REAL_REKOR_TESTS=1` and `TC_API_REAL_REKOR_IDENTITY_TOKEN` are set.
- It validates real bundle signing, public Rekor upload, retrieval, and immutable replay.
- The default migration target now uses Rekor `intoto` uploads and expects replay materialization to come from Rekor-hosted attestation storage before any OCI mirror fallback is attempted.
- It now includes both a direct Event Log 0 bundle smoke test and a fuller `init_chain -> submit -> verify` smoke test for the explicit `default`-chain init path, where baseline records are emitted as Sigstore Bundles.
- It also includes a lazy non-`default` workload-chain smoke test, where the first workload commit causes TruCon to mint Event Log 0 via the same Sigstore/Rekor path before the triggering event is accepted as `sequence_num=2`.
- It now includes an opt-in `intoto` round-trip smoke that clears the adapter cache and expects replayable payload fields to be recovered from Rekor attestation storage.
- It also includes an opt-in `intoto` multi-entry predecessor-proof smoke test that clears the adapter's in-process cache before replay and requires the head record to prove its predecessor through public Rekor plus attestation storage without OCI mirror.
- A separate DSSE regression smoke remains in place to document the previous public replay limit on canonicalized DSSE bodies.
- It also includes an opt-in real Rekor + real OCI mirror + real verify multi-chain smoke that requires the head record to re-materialize DSSE payload fields through the mirror after the in-process cache is cleared.
- Immutable replay now uses signed `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, with Rekor `payloadHash(sha256)` lookup serving as candidate discovery only.
- Mixed-regime rollout behavior is still primarily covered by local regression tests rather than live public-Rekor integration.
- The dedicated predecessor-proof smoke tests intentionally clear the adapter's in-process cache before replay to validate the public candidate-discovery path separately. Same-process cache may still be used as a local fallback during debugging, but cache-assisted replay no longer counts as public proof in verifier results.

The recent public-Rekor `intoto` debugging cycle also established the concrete submission contract that tc_api now relies on for Rekor `intoto` v0.0.2 uploads:

- the proposed entry must set top-level `apiVersion` to `0.0.2`; leaving the generated client default at `0.0.1` causes Rekor to validate against the legacy schema and surface errors such as `publicKey in body is required`;
- `spec.content.envelope.payload` and each signature `sig` must be encoded the way Rekor v0.0.2 expects for its direct decoder path, matching the server-side `CreateFromArtifactProperties()` behavior rather than simply forwarding DSSE JSON fields verbatim; a mismatch shows up as `could not verify envelope: unable to base64 decode payload`;
- `spec.content.hash` must be present on upload and must equal the `sha256` digest of the original DSSE envelope JSON; omitting that field can reach Rekor's type-specific unmarshal path but still fail later with `500: error generating canonicalized entry` when canonicalization requires the envelope digest.

These checks are now covered by focused adapter unit tests and should be treated as a compatibility contract for future Sigstore/Rekor library updates.

Recommended selectors when validating the new migration target explicitly:

```bash
TC_API_RUN_REAL_REKOR_TESTS=1 \
TC_API_REAL_REKOR_IDENTITY_TOKEN='<oidc-jwt>' \
python -m pytest \
   tests/test_real_rekor_integration.py::test_public_rekor_intoto_round_trip_materializes_attestation_payload \
   tests/test_real_rekor_integration.py::test_public_rekor_intoto_multi_entry_predecessor_proof_without_mirror -q
```

Rollback guidance if public Rekor stops returning usable attestation-storage material:

- set `TC_API_REKOR_ENTRY_TYPE=dsse` for the adapter path to restore DSSE-type uploads while keeping verifier-side attestation support available for future re-enable;
- keep the DSSE regression smoke enabled so the public replay limit remains documented rather than silently changing expectations;
- continue using `--mirror-dir` and, where appropriate, `--require-mirror` so OCI mirror remains the explicit fallback while the public Rekor assumption is being revalidated.

## Verification Result Diagnostics

`tc-verify --json` now emits a stable top-level `diagnostics` object alongside `summary`, `replay`, `fallback`, and `entries`.

Use it first when a smoke run fails. It summarizes:

- `diagnostics.replay.success` and `diagnostics.replay.provenance_status`;
- `diagnostics.fallback.valid` and `diagnostics.fallback.rtmr_available`;
- `diagnostics.first_error`;
- `diagnostics.replay.first_entry_issue`, which points at the first entry with `boundary_status`, `public_history_status`, predecessor failure, or replay errors.

### Short-Lived Token Guidance

The public Rekor smoke test typically uses an OIDC token with an approximately 1-minute validity window. That is acceptable for manual integration testing, but it should be treated as a just-in-time credential and not as a deploy-time configuration value.

Practical guidance:

- acquire the token immediately before running the test, preferably with `tc-oidc-preflight --fetch --run-real-rekor-smoke`;
- do not expect a manually exported token to survive multiple retries or long debugging pauses;
- if the token expires, reacquire it rather than reusing the old environment variable;
- keep preflight checks and the live pytest invocation close together in time.

This short lifetime does not, by itself, create a production design problem. In an actual deployment, the service should not rely on a human-exported static token. Instead it should obtain a fresh ambient or workload identity token just before each signing operation and let Sigstore exchange that short-lived token for the signing certificate immediately.

In other words:

- manual exported token: suitable for opt-in smoke tests only;
- automatic just-in-time token acquisition: suitable for deployed services.

`--require-tee` should fail when TruCon reports non-TEE fallback mode. Non-TEE verification remains suitable for development and test environments only.

Prefer exported evidence as the primary operator input. Bare `tc-verify <chain_id>` is no longer a supported external verification path; local live verification now requires an explicit troubleshooting selector and should be treated as internal diagnostics only.

Migration guidance:

- use `tc-verify --evidence evidence.json` for supported operator verification;
- use the explicit live troubleshooting mode only for local diagnostics, pending-state inspection, or tightly coupled debugging;
- do not treat troubleshooting-mode output as a replacement for the external verifier contract.

## Test Coverage

### API Endpoints Tested

1. **Health Check** (`GET /`)
   - ✅ Service availability
   - ✅ Response format validation

2. **Build Package** (`POST /api/build-package`)
   - ✅ Successful build submission
   - ✅ Build with encryption enabled
   - ✅ Invalid data validation
   - ✅ Build ID generation

3. **Build Result** (`GET /api/build-result/{build_id}`)
   - ✅ Successful result retrieval
   - ✅ Non-existent build handling
   - ✅ Status progression tracking

4. **Publish Package** (`PUT /api/publish-package`)
   - ✅ Successful image publishing
   - ✅ SBOM handling
   - ✅ Metadata processing

5. **Register Key** (`POST /api/keys/register`)
   - ✅ Successful key registration
   - ✅ Policy validation
   - ✅ Invalid data handling

6. **Get Artifact** (`GET /api/artifacts/{build_id}/{artifact_type}`)
   - ✅ Artifact retrieval
   - ✅ Non-existent artifact handling

### Test Types

- **Unit Tests**: Individual API endpoint functionality
- **Integration Tests**: Complete workflow testing
- **Performance Tests**: Concurrent request handling
- **Validation Tests**: Input validation and error handling

## Sample Test Data

The tests use sample data including:
- Mock Dockerfile for nginx-based container
- Sample private/public key pairs (for testing only)
- Sample certificates
- Mock SBOM data

## Expected Behavior

### Successful Test Run Output

```
TC API Comprehensive Test Suite
============================================================
Testing health check...
Status: 200
Response: {'message': 'TC API Service is running', 'timestamp': '...'}
--------------------------------------------------
Testing build package...
Status: 200
Build ID: bld-1234567890
Status: submitted
Estimated Time: 120s
--------------------------------------------------
...
============================================================
All tests completed successfully!
```

### Common Issues

1. **Connection Error**: Make sure the TC API service is running
2. **Build Failures**: Check that Docker tools are available (for actual implementation)
3. **Validation Errors**: Verify request payload format matches API schema

## Continuous Integration

To run tests in CI/CD pipeline:

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
python -m tests.test_runner --type all --verbose
```

## Test Development

To add new tests:

1. For manual tests: Add functions to `tests/test_api.py`
2. For automated tests: Add methods to appropriate class in `tests/test_unit.py`
3. Use descriptive test names and include docstrings
4. Test both success and failure scenarios
5. Clean up any resources created during tests

## Mocking External Dependencies

The current implementation uses mock responses for external tools:
- Docker commands are simulated
- Cosign signing is mocked
- Syft SBOM generation is simulated
- KBS service calls are mocked

For production testing, consider using actual tool integrations or more sophisticated mocking.

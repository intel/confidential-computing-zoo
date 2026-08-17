# OpenClaw Agent Example

This directory contains an example adapter that demonstrates how OpenClaw integrates with Agent-CC as a runtime trust verification framework.

## Overview

OpenClaw is an AI agent runtime in a standard process. It uses Agent-CC core services for trusted agent-to-service communication:

- **OpenClaw** (caller): the agent runtime running in a standard environment, which makes trust decisions based on Argus verification results
- **OpenViking** (service side): a trusted workload running inside a TDVM
- **Argus Guard**: verifies OpenViking's TDX attestation evidence on behalf of OpenClaw
- **Argus Provider** (service side): generates TDX quotes for OpenViking inside the TDVM

This example shows how OpenClaw uses Argus to verify the identity and runtime state of a remote service before exchanging sensitive data.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent Runtime                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw Agent (standard process)                          │ │
│  │  - LLM Client                                               │ │
│  │  - Context Manager                                          │ │
│  │  - Tool Executor                                            │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │ Attestation-gated context transfer
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   OpenViking Service (TDVM)                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenViking Confidential Memory Control Plane              │ │
│  │  - Context Gateway                                          │ │
│  │  - Encrypted Storage                                        │ │
│  │  - Trust Policy Engine                                      │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-CC Core Services                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Argus     │  │   TC-API    │  │  Trust      │              │
│  │  Verifier   │  │  Service    │  │  Service    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

## Implementation Files

| File | Description |
|------|-------------|
| [scripts/openclaw_agent.py](scripts/openclaw_agent.py) | Working Python implementation |
| [scripts/run_openclaw_openviking_e2e.sh](scripts/run_openclaw_openviking_e2e.sh) | One-click real-quote end-to-end run script |
| [README.md](README.md) | English documentation |
| [README_CN.md](README_CN.md) | Chinese documentation |

## Integration Points

### 1. Evidence Provider Integration

OpenClaw obtains TDX attestation evidence through the Agent-CC Evidence Provider:

```rust
// Example: obtain attestation evidence for the OpenClaw runtime
use argus::EvidenceFetcher;

pub struct OpenClawEvidenceProvider {
    evidence_endpoint: String,
}

impl OpenClawEvidenceProvider {
    pub fn new() -> Self {
        Self {
            evidence_endpoint: std::env::var("EVIDENCE_ENDPOINT")
                .unwrap_or_else(|_| "http://localhost:8008".to_string()),
        }
    }

    /// Obtain the TDX quote attesting the OpenClaw runtime
    pub async fn fetch_runtime_attestation(&self) -> Result<AttestationEvidence> {
        let evidence = EvidenceFetcher::new(&self.evidence_endpoint)
            .with_service_identity("openclaw-agent")
            .fetch_evidence()
            .await?;

        Ok(AttestationEvidence {
            quote: evidence.tdx_quote,
            runtime_measurements: evidence.rtmr_values,
            tcb_status: evidence.tcb_status,
        })
    }
}
```

### 2. Attestation-Based Secret Release

OpenClaw retrieves secrets only after attestation verification succeeds:

```rust
// Example: retrieve API keys based on attestation
use argus::{AttestationContext, SecretStore};

pub struct OpenClawSecretManager {
    secret_store: SecretStore,
}

impl OpenClawSecretManager {
    /// Obtain the API key only if attestation succeeds
    pub async fn get_api_key(&self, key_id: &str) -> Result<String> {
        let attestation = AttestationContext::new()
            .with_minimum_assurance_level("L2")
            .verify()
            .await?;

        if !attestation.is_trusted() {
            return Err(AgentError::AttestationFailed {
                reason: "OpenClaw runtime attestation verification failed".to_string(),
            });
        }

        self.secret_store
            .get_secret(key_id, &attestation)
            .await
    }
}
```

### 3. Encrypted Context Storage

OpenClaw uses Agent-CC encrypted storage to persist sensitive context:

```rust
// Example: encrypted context storage with attestation binding
use argus::{EncryptedStorage, AttestationBinding};

pub struct OpenClawContextManager {
    storage: EncryptedStorage,
}

impl OpenClawContextManager {
    /// Store context with attestation binding
    pub async fn store_context(
        &self,
        context_id: &str,
        context_data: &[u8],
        binding: &AttestationBinding,
    ) -> Result<()> {
        self.storage
            .store_encrypted(context_id, context_data, binding)
            .await
    }

    /// Retrieve context only when the attestation binding matches
    pub async fn retrieve_context(
        &self,
        context_id: &str,
        expected_binding: &AttestationBinding,
    ) -> Result<Vec<u8>> {
        let context = self.storage
            .retrieve_encrypted(context_id, expected_binding)
            .await?;

        Ok(context)
    }
}
```

## Configuration

### Environment Variables

```bash
# OpenClaw Agent configuration
AGENT_SERVICE_NAME=openclaw-agent
AGENT_INSTANCE_ID=openclaw-instance-001

# Evidence Provider
EVIDENCE_ENDPOINT=http://localhost:8008

# Guard Service (for service-to-service attestation)
GUARD_ENDPOINT=http://localhost:8007
BINDING_ASSURANCE_LEVEL=L2

# Encrypted storage
ENCRYPTED_VFS_PATH=/mnt/encrypted
```

### Configure Ollama as the OpenClaw primary model

Configures Ollama for OpenClaw's primary model. Ollama must expose the OpenAI-compatible API, and the target model must be downloaded in advance:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
./run_ollama_luks.sh pull llama3.2
OLLAMA_HOST=0.0.0.0:11434 ./run_ollama_luks.sh serve
```

`run_ollama_luks.sh` requires `OLLAMA_LUKS_MOUNT_ROOT` to be an active LUKS
mount point and stores models under `${OLLAMA_LUKS_MOUNT_ROOT}/ollama` by
default. Do not run plain `ollama serve` or `ollama pull`, because the default
path `~/.ollama/models` is outside the LUKS-protected storage. Keep the `serve`
command running in a separate terminal while completing the steps below.

Run the connector after the OpenClaw Gateway is running with a persistent config
volume:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
export OPENCLAW_CONTAINER=agentcc-openclaw-sbx-gateway
export OLLAMA_BASE_URL=http://127.0.0.1:11434
export OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11434
export OLLAMA_MODEL=llama3.2
./connect_openclaw_ollama.sh
```

`OLLAMA_BASE_URL` is used by the script on the host. `OLLAMA_CONTAINER_BASE_URL`
is written to the OpenClaw configuration and must be reachable from the Gateway
container. On Linux, create the container with
`--add-host=host.docker.internal:host-gateway`, or set this variable to an
Ollama address on a shared Docker network. The `OLLAMA_HOST` setting in the
server command above makes Ollama listen on an address accessible to the
container; restrict host firewall access to trusted clients.

The script verifies Ollama readiness, model availability, and container access;
then it writes `models.providers.ollama` and sets
`agents.defaults.model.primary` to `ollama/llama3.2`. This step does not require
Argus Guard, the Evidence Provider, or TC-API; it validates only the model-call
path. For an attested deployment, register Ollama as an independent `ollama-llm`
workload and allow OpenClaw to access it only after Argus verification.

### Docker Compose Example

```yaml
# filepath: docker-compose.yml
services:
  openclaw-agent:
    image: openclaw:latest-tdx
    environment:
      HOST: 0.0.0.0
      PORT: 8009
      EVIDENCE_ENDPOINT: http://argus-evidence-provider:8008
      GUARD_ENDPOINT: http://argus-guard:8007
      BINDING_ASSURANCE_LEVEL: L2
      ENCRYPTED_VFS_PATH: /mnt/encrypted
    volumes:
      - encrypted_vfs:/mnt/encrypted
    depends_on:
      - argus-evidence-provider
      - argus-guard
    devices:
      - /dev/tdx_guest:/dev/tdx_guest
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined

  argus-evidence-provider:
    image: argus-evidence-provider:latest
    environment:
      HOST: 0.0.0.0
      PORT: 8008
      RUST_LOG: info
    volumes:
      - tsm_socket:/var/run/tsm

  argus-guard:
    image: argus-guard:latest
    environment:
      HOST: 0.0.0.0
      PORT: 8007
      EVIDENCE_ENDPOINT: http://argus-evidence-provider:8008
      BINDING_ASSURANCE_LEVEL: L2
      RUST_LOG: info

volumes:
  encrypted_vfs:
```

## Verification Flow

```
1. OpenClaw starts inside the TDVM
         │
         ▼
2. Obtain a TDX Quote from the TSM
         │
         ▼
3. Send it to the Evidence Provider
         │
         ▼
4. Argus verifies the quote structure
         │
         ▼
5. Argus verifies nonce binding
         │
         ▼
6. Argus checks TCB status
         │
         ▼
7. Return attestation evidence
         │
         ▼
8. OpenClaw uses the evidence for:
   - Service attestation
   - Secret retrieval
   - Encrypted storage access
```

## Example Run

### Prerequisites

- On the OpenClaw side: Argus Guard is reachable at `http://localhost:8007`
- On the OpenViking side: Argus Evidence Provider is reachable from the Guard host
- If you need the real-quote path, an Intel TDX platform with TSM enabled is required

### Build and Run

```bash
# On the OpenClaw side, start only Argus Guard and point it to the provider on the OpenViking side.
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008
./start_argus.sh start-guard

# Return to the OpenClaw example on the same host.
cd ../../../adapters/OpenClaw/scripts

# Optional: override the logical target that OpenClaw verifies
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=https://<openviking-service-host>

# Run the caller-side verification demo
python3 openclaw_agent.py
```

On the OpenViking side, start the provider separately:

```bash
cd ../../../core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
./start_argus.sh start-provider
```

## Expected Output

```bash
OpenClaw Agent - Agent-CC Integration Example

[1] Verifying OpenViking through Argus Guard...
    TCB Status: UpToDate
    Service Name: openviking-cmem
    Workload ID: openviking-cmem
    Launch ID: launch-...
    Image Digest: sha256:...
    Rekor UUID: ...
    Transparency Log ID: ...
    RTMR0: ...

[2] Creating attestation context...
[3] Retrieving attestation-gated secret...
[4] Storing context with attestation binding...
[5] Retrieving context with binding verification...
```

On the current live TSM path, after quote structure validation and request-binding validation succeed, Argus reports `TCB Status: UpToDate`. This is sufficient for the example's default policy flow, but it still does not indicate that collateral-based TCB freshness evaluation has been completed.

The additional metadata lines above appear only when the OpenViking side is started through the tc-api-managed Docker path. Running `python3 openviking_service.py --serve` directly can still return attestation evidence, but tc-api-specific fields such as image digest, launch ID, and Rekor UUID remain empty unless tc-api is tracking the service workload.

## tc-api-Based OpenViking Deployment

To display `image_digest`, `launch_id`, and Rekor identifiers in Argus claims, the OpenViking side must be started through tc-api or another Docktap-managed Docker path instead of running only the Python demo directly.

1. Start tc-api on the OpenViking side.
2. Start the OpenViking workload through `POST /api/deploy-launch` and set `metadata.workload_id` to `openviking-cmem`.
3. Start the sidecar/provider process with `ARGUS_SERVICE_ID=openviking-cmem` and `TC_API_WORKLOAD_ID=openviking-cmem` so that Argus queries tc-api by workload ID rather than by its own container ID.
4. Point the Guard on the OpenClaw side to that provider: `EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008`.

Example provider-side environment variables:

```bash
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## See Also

- [OpenClaw Adapter](../README.md) - Main adapter documentation
- [Argus Verifier](../../core/argus/README.md) - TDX quote verification
- [TC-API Service](../../core/tc-api/README.md) - Build-to-runtime trust

## Quick Start

### Prerequisites

Before running the full end-to-end test, make sure you have:
- an Intel TDX-enabled platform (`/dev/tdx_guest`)
- TSM configfs at `/sys/kernel/config/tsm/report/`
- Docker and docker-compose installed
- Argus binaries built (see [core/argus README](../../core/argus/README.md))
- a TC-API identity token set (`TC_API_IDENTITY_TOKEN` or `TC_API_BEARER_TOKEN`)

`TC_API_IDENTITY_TOKEN` is not a fixed value auto-generated by the repository. It is a short-lived Sigstore OIDC identity token. In this end-to-end path, the most direct way to obtain it is to reuse the tc-api CLI included in the repository to complete an interactive Sigstore login, then export the returned value as `TC_API_IDENTITY_TOKEN`.

### Step 1: Validate the Environment

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/core/argus
./start_argus.sh validate
```

Expected output:
```
[INFO] Validating environment...
[INFO] TDX device found at /dev/tdx_guest
[INFO] TSM configfs found
```

### Step 2: Build Argus (if not already built)

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/core/argus
cargo build --release
```

### Step 3: Obtain `TC_API_IDENTITY_TOKEN`

It is recommended to use the CLI built into tc-api for OOB (out-of-band) Sigstore login and directly output shell variables that can be `eval`'d:

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/core/tc_api
bash setup.sh
eval "$(./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format export --env-var TC_API_IDENTITY_TOKEN)"
```

After execution, a Sigstore login flow will open or be prompted; once login is complete, the command will export `TC_API_IDENTITY_TOKEN` in the current shell. You can confirm that the variable exists with:

```bash
env | grep '^TC_API_IDENTITY_TOKEN='
```

Notes:
- This is a short-lived token. After it expires, rerun the login command above.
- If `tc-client` is already installed into your `PATH`, you can also run it directly:

```bash
eval "$(tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format export --env-var TC_API_IDENTITY_TOKEN)"
```

- If your tc-api deployment uses HTTP Authorization header authentication, you can instead export `TC_API_BEARER_TOKEN` in advance; however, in the current repository examples, using `TC_API_IDENTITY_TOKEN` is more direct.

### Step 4: Execute the End-to-End Flow in Three Steps (Recommended)

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenClaw/scripts
```

#### 4.1 Service Side: Start OpenViking via tc-api

```bash
# Requires TC_API_IDENTITY_TOKEN or TC_API_BEARER_TOKEN
./step1_launch_openviking_via_tc_api.sh
```

This phase will:
1. start the compose stack (registry + tc-api + argus-provider)
2. start the OpenViking workload through `POST /api/deploy-launch`

Common environment variables:
- `TC_API_IDENTITY_TOKEN` / `TC_API_BEARER_TOKEN` (required unless already running and launch is skipped)
- `TC_API_URL` (default `http://127.0.0.1:8000`)
- `TARGET_URI` (default `http://127.0.0.1:8010`)
- `TARGET_SERVICE_NAME` (default `openviking-cmem`)
- `FORCE_LAUNCH=1` (force relaunch)
- `SKIP_OPENVIKING_LAUNCH=1` (start only the control plane without launching)

#### 4.2 Agent Side: Start OpenClaw via tc-api (see `openclaw_container_protection.md`)

```bash
# Optional step; not run by default; used to bring OpenClaw itself under tc-api launch management
RUN_STEP2_OPENCLAW=1 ./step2_launch_openclaw_via_tc_api.sh
```

This phase will:
1. build and push the OpenClaw image by default
2. start the OpenClaw workload through tc-api `deploy-launch`

Common environment variables:
- `TC_API_IDENTITY_TOKEN` / `TC_API_BEARER_TOKEN` (required)
- `OPENCLAW_IMAGE_NAME`, `OPENCLAW_IMAGE_URL`, `OPENCLAW_IMAGE_ID`
- `OPENCLAW_DOCKERFILE`, `OPENCLAW_BUILD_CONTEXT`
- `OPENCLAW_BUILD_IMAGE=0|1`, `OPENCLAW_PUSH_IMAGE=0|1`
- `OPENCLAW_WORKLOAD_ID`, `OPENCLAW_USER_ID`
- `OPENCLAW_DOCKERCMD` (optional, passed to tc-api deploy-launch)

#### 4.3 Communication Side: Use Argus to Establish Communication Between OpenClaw and OpenViking

```bash
./step3_connect_openclaw_openviking_via_argus.sh
```

This phase will:
1. start `argus-guard` in real-verifier mode
2. run `openclaw_agent.py` to complete the communication chain OpenClaw -> Guard -> Provider -> OpenViking

Common environment variables:
- `PROVIDER_URL` (default `http://127.0.0.1:8008`)
- `GUARD_URL` (default `http://127.0.0.1:8007`)
- `TARGET_URI`, `TARGET_SERVICE_NAME`
- `OPENCLAW_PYTHON`, `RUST_LOG`

#### 4.4 Keep the One-Click Orchestration Entry Point

```bash
# Runs step1 + step3 by default
./run_openclaw_openviking_e2e.sh

# Runs step1 + step2 + step3
RUN_STEP2_OPENCLAW=1 ./run_openclaw_openviking_e2e.sh
```

## Verification Status

As of 2026-06-29, the following has been verified with real runs:

- tc-api `deploy-launch` succeeds under interactive Sigstore login and starts a running OpenViking workload listening on `http://127.0.0.1:8010`.
- Argus provider can now return claims with tc-api metadata, including `launch_id`, `image_digest`, and `transparency_log_id`.
- Argus provider can now generate a real TDX quote through tc-api `POST /v1/attestation`, no longer falling back to mock evidence.
- Guard can now successfully accept the quote returned by the provider in real-verifier mode without setting `ARGUS_ALLOW_MOCK_VERIFIER=1`.
- `openclaw_agent.py` has now completed the following real end-to-end chain: OpenClaw -> Guard -> Provider -> OpenViking `POST /verify/caller` -> `POST /context` -> `GET /context/{id}/metadata` -> `GET /context/{id}`.

- The OpenClaw side can reach the local Argus Guard: `http://localhost:8007`
- The OpenViking side runs Argus Evidence Provider separately, and Guard can reach it
- If you want the real-quote path, the current machine must support Intel TDX and TSM

## Real Dual-Side Deployment Steps

```bash
# In the OpenViking example directory, start compose, launch the workload, start real Guard, and execute OpenClaw in one step.
cd ../../OpenViking/examples
./run_openclaw_openviking_e2e.sh
```

## Expected Output

```text
OpenClaw Agent - Agent-CC Integration Example

[1] Verifying OpenViking through Argus Guard...
    TCB Status: Unknown
    Service Name: openviking-cmem
    Workload ID: openviking-cmem
    Launch ID: launch-...
    Image Digest: sha256:...
    Rekor UUID: ...
    Transparency Log ID: ...
    RTMR0: ...

[2] Creating attestation context...
[3] Retrieving attestation-gated secret...
[4] Storing context with attestation binding...
[5] Retrieving context with binding verification...
```

In the live TSM path in the current repository, after quote structure validation and request-binding validation pass, `TCB Status` is shown as `Unknown`. This is the explicit semantic of the current implementation: Argus has not yet integrated collateral-driven TCB freshness evaluation, so it does not claim `UpToDate`.

These extra metadata lines appear only when the OpenViking side is started through the tc-api-managed Docker / launch path. Running `python3 openviking_service.py --serve` on its own can still return attestation results, but if tc-api is not tracking that workload, tc-api-related fields such as `image_digest`, `launch_id`, and `Rekor UUID` will not be included.

## tc-api-Based OpenViking Deployment

If you want Argus claims to include `image_digest`, `launch_id`, and Rekor identifiers, the OpenViking side must be started through tc-api or another Docktap-managed Docker path rather than running only the Python demo.

1. Start tc-api on the OpenViking side.
2. Start the OpenViking workload through `POST /api/deploy-launch` and set `metadata.workload_id` to `openviking-cmem`.
3. Set `ARGUS_SERVICE_ID=openviking-cmem` and `TC_API_WORKLOAD_ID=openviking-cmem` for the sidecar/provider process so Argus queries tc-api by workload ID rather than by the provider's own container ID.
4. On the OpenClaw side, point the Guard `EVIDENCE_ENDPOINT` at that provider: `http://<openviking-provider-host>:8008`.

Example provider-side environment variables:

```bash
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

## Implementation Files

| File | Description |
|------|-------------|
| [openclaw_agent.py](openclaw_agent.py) | Working Python implementation |
| [README.md](README.md) | English documentation |
| [README_CN.md](README_CN.md) | Chinese documentation |

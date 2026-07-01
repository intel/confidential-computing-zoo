# OpenClaw Agent Example

This directory contains an example adapter demonstrating how OpenClaw integrates with Agent-CC as an agent runtime.

## Overview

OpenClaw is an agent runtime that runs inside a TDVM (Trust Domain Virtual Machine) for confidential AI agent execution. This example shows how OpenClaw uses Agent-CC's core services for attestation-gated operations.

## Implementation Files

| File | Description |
|------|-------------|
| [openclaw_agent.py](openclaw_agent.py) | Working Python implementation |
| [README.md](README.md) | This documentation |

## Quick Start

### Prerequisites

Before running the full e2e test, ensure:
- Intel TDX-enabled platform with `/dev/tdx_guest`
- TSM configfs at `/sys/kernel/config/tsm/report/`
- Docker & docker-compose installed
- Argus binaries built (see [core/argus README](../../core/argus/README.md))
- TC-API identity token (set `TC_API_IDENTITY_TOKEN` or `TC_API_BEARER_TOKEN`)

### Step 1: Validate Environment

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
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
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
cargo build --release
```

### Step 3: Run Full End-to-End Test

```bash
# One-shot real quote path: compose stack + tc-api launch + real Guard + OpenClaw.
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenViking/examples
export TC_API_IDENTITY_TOKEN=<sigstore-identity-token>
./run_openclaw_openviking_e2e.sh
```

This script:
1. Starts Docker Compose stack (registry + tc-api + argus-provider)
2. Launches OpenViking workload via tc-api
3. Starts argus-guard in real-verifier mode
4. Runs OpenClaw verification with full TDX attestation

### Skip Workload Launch (if already running)

If the OpenViking workload is already running and healthy on `:8010`, rerun the
same script with `SKIP_LAUNCH=1` to skip the tc-api launch step:

```bash
SKIP_LAUNCH=1 ./run_openclaw_openviking_e2e.sh
```

For the real tc-api-backed Docker flow, the OpenViking side can now use
`docker-compose.tc-api.yml` plus `launch_openviking_via_tc_api.sh` from the
OpenViking example directory. The new `run_openclaw_openviking_e2e.sh` wrapper
now stitches that path together with a real-verifier Guard run and the final
OpenClaw verification.

The example calls `POST /ra/v1/verify` on the local Argus Guard and treats the
returned `report_data` as the binding digest for local secret release and
context storage.

## Validation Status

Verified on 2026-06-29:

- Real tc-api interactive `deploy-launch` succeeded and produced a running
    OpenViking workload on `http://127.0.0.1:8010`.
- Argus provider returned tc-api-backed claims including `launch_id`,
    `image_digest`, and `transparency_log_id`.
- Argus provider generated a real TDX quote via tc-api `POST /v1/attestation`
    instead of falling back to mock evidence.
- Guard accepted the provider quote in real verifier mode without
    `ARGUS_ALLOW_MOCK_VERIFIER=1`.
- `openclaw_agent.py` completed a real end-to-end flow:
    OpenClaw -> Guard -> Provider -> OpenViking `POST /verify/caller` ->
    `POST /context` -> `GET /context/{id}/metadata` -> `GET /context/{id}`.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Agent-CC Core Services                      │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Argus     │  │   TC-API    │  │  Trust      │              │
│  │  Verifier   │  │  Service    │  │  Service    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent Runtime                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw Agent (TDVM)                                      │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │ │
│  │  │   LLM       │  │  Context   │  │   Tools     │          │ │
│  │  │   Client    │  │  Manager    │  │  Executor   │          │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘          │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Integration Points

### 1. Evidence Provider Integration

OpenClaw fetches TDX attestation evidence through the Agent-CC Evidence Provider:

```rust
// Example: Fetch attestation evidence for OpenClaw runtime
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

    /// Fetch TDX quote for OpenClaw runtime attestation
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

### 2. Attestation-Gated Secret Release

OpenClaw retrieves secrets only after attestation verification succeeds:

```rust
// Example: Attestation-gated API key retrieval
use argus::{AttestationContext, SecretStore};

pub struct OpenClawSecretManager {
    secret_store: SecretStore,
}

impl OpenClawSecretManager {
    /// Retrieve API key only if attestation passes
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

OpenClaw uses Agent-CC's encrypted storage for sensitive context:

```rust
// Example: Encrypted context storage with attestation binding
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

    /// Retrieve context only if attestation matches
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
# OpenClaw Agent Configuration
AGENT_SERVICE_NAME=openclaw-agent
AGENT_INSTANCE_ID=openclaw-instance-001

# Evidence Provider
EVIDENCE_ENDPOINT=http://localhost:8008

# Guard Service (for service-to-service attestation)
GUARD_ENDPOINT=http://localhost:8007
BINDING_ASSURANCE_LEVEL=L2

# Encrypted Storage
ENCRYPTED_VFS_PATH=/mnt/encrypted
```

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
1. OpenClaw starts in TDVM
         │
         ▼
2. Fetch TDX Quote from TSM
         │
         ▼
3. Send to Evidence Provider
         │
         ▼
4. Argus verifies quote structure
         │
         ▼
5. Argus verifies nonce binding
         │
         ▼
6. Argus checks TCB status
         │
         ▼
7. Return Attestation Evidence
         │
         ▼
8. OpenClaw uses evidence for:
   - Service attestation
   - Secret retrieval
   - Encrypted storage access
```

## Running the Example

### Prerequisites

- OpenClaw side: Argus Guard reachable at `http://localhost:8007`
- OpenViking side: Argus Evidence Provider reachable from the Guard host
- Intel TDX-enabled platform with TSM enabled if you want a real quote path

### Build and Run

```bash
# On the OpenClaw side, start only Argus Guard and point it at the
# OpenViking-side provider.
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008
./start_argus.sh start-guard

# Return to the OpenClaw example on the same host.
cd ../../../adapters/OpenClaw/examples

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

On the current live TSM path, Argus reports `TCB Status: UpToDate` after quote
structure and request-binding verification succeed. That is sufficient for the
example's default policy flow, but it still does not imply collateral-backed
TCB freshness evaluation.

The extra metadata lines above appear only when the OpenViking side is launched
through a tc-api-managed Docker path. Plain `python3 openviking_service.py --serve`
can still return attestation evidence, but tc-api-specific fields such as image
digest, launch ID, and Rekor UUID will be empty unless tc-api is tracking the
service workload.

## tc-api-backed OpenViking Deployment

To surface `image_digest`, `launch_id`, and Rekor identifiers in Argus claims,
the OpenViking side needs to be launched through tc-api or another Docktap-managed
Docker path instead of only running the Python demo directly.

1. Start tc-api on the OpenViking side.
2. Launch the OpenViking workload through `POST /api/deploy-launch` and set `metadata.workload_id` to `openviking-cmem`.
3. Start the sidecar/provider process with both `ARGUS_SERVICE_ID=openviking-cmem` and `TC_API_WORKLOAD_ID=openviking-cmem` so Argus queries tc-api by workload ID instead of its own container ID.
4. Point the OpenClaw-side Guard at that provider with `EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008`.

Example provider-side environment:

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
- [Trust Service](../../core/trust-service/README.md) - Attestation support
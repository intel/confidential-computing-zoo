# OpenViking Service Example

This directory contains an example adapter demonstrating how OpenViking integrates with Agent-CC as a confidential memory service.

## Overview

OpenViking is a confidential memory control plane service that provides attestation-gated context storage and retrieval. This example shows how OpenViking uses Agent-CC's core services for trusted context transfer.

## Implementation Files

| File | Description |
|------|-------------|
| [openviking_service.py](openviking_service.py) | Working Python implementation |
| [Dockerfile.tc-api-workload](Dockerfile.tc-api-workload) | Container image for tc-api-managed OpenViking workload |
| [docker-compose.tc-api.yml](docker-compose.tc-api.yml) | tc-api + registry + Argus Provider stack for the real Docker launch flow |
| [launch_openviking_via_tc_api.sh](launch_openviking_via_tc_api.sh) | Builds, pushes, and launches the OpenViking workload through tc-api |
| [run_openclaw_openviking_e2e.sh](run_openclaw_openviking_e2e.sh) | One-shot real quote e2e runner for tc-api + Provider + Guard + OpenClaw |
| [README.md](README.md) | This documentation |

## Quick Start

### Prerequisites

Before running, ensure you have:
- Intel TDX-enabled platform with `/dev/tdx_guest`
- Linux kernel 5.15+ with TSM configfs at `/sys/kernel/config/tsm/report/`
- Rust 1.75+
- Docker & docker-compose
- TC-API identity token (set `TC_API_IDENTITY_TOKEN` or `TC_API_BEARER_TOKEN`)

### Step 1: Validate TDX Environment

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/argus
./start_argus.sh validate
```

Expected output:
```
[INFO] Validating environment...
[INFO] Rust version: 1.96.0
[INFO] TDX device found at /dev/tdx_guest
[INFO] TSM configfs found
[INFO] TSM report interface available
```

### Step 2: Build Argus Binaries

```bash
cargo build --release
```

### Step 3: Start Docker Compose Stack

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenViking/examples
docker-compose -f docker-compose.tc-api.yml up -d
```

Wait for services to be healthy:
```bash
curl http://127.0.0.1:8000/      # tc-api
curl http://127.0.0.1:8008/health  # argus-provider
```

### Step 4: Run Full End-to-End Test

For the complete real TDX quote attestation flow:

```bash
# Set your TC-API token
export TC_API_IDENTITY_TOKEN="your-token-here"

# Run the e2e test
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenViking/examples
./run_openclaw_openviking_e2e.sh
```

This script:
1. Starts the compose stack (registry + tc-api + argus-provider)
2. Launches the OpenViking workload via tc-api
3. Starts argus-guard in real-verifier mode
4. Runs the OpenClaw example with full TDX attestation

### Alternative: Run OpenViking Service Only (Demo Mode)

For a quick in-memory demo without full attestation:

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenViking/examples
python3 openviking_service.py
```

Or start the HTTP gateway for manual testing:

```bash
python3 openviking_service.py --serve
```

> **Note**: The demo mode (`openviking_service.py`) runs in-memory without real TDX quotes. For production or full attestation validation, use `run_openclaw_openviking_e2e.sh`.

OpenViking itself does not start the Argus Evidence Provider. The intended flow
is to start only the provider on the OpenViking side with
`ARGUS_WORKLOAD_IDENTITY=openviking-cmem`, while the OpenClaw side runs its own
local Guard with `EVIDENCE_ENDPOINT` pointed at this remote provider.

If you want tc-api-backed metadata such as `image_digest`, `launch_id`, and
Rekor identifiers to show up in Argus claims, the provider should also be given
`ARGUS_SERVICE_ID` and `TC_API_WORKLOAD_ID` matching the workload ID that tc-api
assigned to the OpenViking Docker workload.

The runnable example defaults to `STRICT_MODE=false`. On the current live TSM
path, Argus returns `TCB Status: UpToDate` after quote structure and request
binding verification succeed. That is enough for the example's default policy
flow, but it still does not mean collateral-backed TCB freshness was evaluated.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    OpenClaw Agent Runtime                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  OpenClaw Agent (TDVM)                                      │ │
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

## Integration Points

### 1. Trust Gate Verification

OpenViking implements a verify-skill trust gate that OpenClaw calls before context transfer:

```rust
// Example: OpenViking trust gate implementation
use argus::{TdxQuoteVerifier, AttestationContext};

pub struct OpenVikingTrustGate {
    verifier: TdxQuoteVerifier,
    policy: TrustPolicy,
}

impl OpenVikingTrustGate {
    /// Verify OpenClaw before allowing context access
    pub async fn verify_caller(&self, caller_evidence: &AttestationEvidence) -> Result<bool> {
        // Verify the caller's TDX quote
        self.verifier
            .verify_quote(&caller_evidence.tdx_quote)
            .await?;

        // Check TCB status
        if caller_evidence.tcb_status != TcbStatus::UpToDate {
            tracing::warn!("Caller TCB is not up to date");
            return Ok(false);
        }

        // Verify nonce binding for freshness
        if !self.verify_nonce_binding(&caller_evidence.binding_digest) {
            tracing::warn!("Caller nonce binding verification failed");
            return Ok(false);
        }

        // Check against trust policy
        self.policy
            .evaluate(&caller_evidence.claims)
            .await
    }

    /// Allow or deny context transfer based on verification
    pub async fn evaluate_context_transfer(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
    ) -> Result<ContextTransferDecision> {
        let is_trusted = self.verify_caller(caller).await?;

        if is_trusted {
            Ok(ContextTransferDecision::Allow {
                context_id: context_id.to_string(),
                verified_claims: caller.claims.clone(),
            })
        } else {
            Ok(ContextTransferDecision::Deny {
                reason: "Caller verification failed trust policy".to_string(),
            })
        }
    }
}
```

### 2. Context Gateway Operations

OpenViking exposes context operations that are gated by attestation:

```rust
// Example: Context gateway with attestation gating
use argus::{EncryptedStorage, AttestationBinding};

pub struct OpenVikingContextGateway {
    storage: EncryptedStorage,
    policy: TrustPolicy,
}

impl OpenVikingContextGateway {
    /// Observe context (read-only, no materialization)
    pub async fn observe_context(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
    ) -> Result<ContextMetadata> {
        // Verify caller first
        if !self.verify_caller(caller).await? {
            return Err(GatewayError::AccessDenied {
                reason: "Caller verification failed".to_string(),
            });
        }

        // Return metadata only (not actual content)
        let metadata = self.storage
            .get_metadata(context_id)
            .await?;

        Ok(metadata)
    }

    /// Recall context (materialize for processing)
    pub async fn recall_context(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
    ) -> Result<EncryptedContext> {
        // Full verification for materialization
        if !self.verify_caller(caller).await? {
            return Err(GatewayError::AccessDenied {
                reason: "Caller verification failed".to_string(),
            });
        }

        // Check if context requires elevated privileges
        if self.policy.requires_elevation(context_id) {
            let elevation_verified = self.verify_elevation_claims(caller).await?;
            if !elevation_verified {
                return Err(GatewayError::InsufficientPrivileges {
                    context_id: context_id.to_string(),
                });
            }
        }

        // Return encrypted context
        let context = self.storage
            .retrieve_encrypted(context_id, &caller.binding)
            .await?;

        Ok(context)
    }

    /// Commit new context (archive with encryption)
    pub async fn commit_context(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
        content: &[u8],
    ) -> Result<CommitReceipt> {
        // Verify caller can write
        if !self.verify_caller(caller).await? {
            return Err(GatewayError::AccessDenied {
                reason: "Caller verification failed".to_string(),
            });
        }

        // Encrypt and store with caller's binding
        let binding = self.compute_binding(caller);
        self.storage
            .store_encrypted(context_id, content, &binding)
            .await?;

        Ok(CommitReceipt {
            context_id: context_id.to_string(),
            committed_at: chrono::Utc::now(),
            binding: binding.digest,
        })
    }
}
```

### 3. Privacy Restore

OpenViking supports privacy restore operations:

```rust
// Example: Privacy restore with attestation verification
pub struct OpenVikingPrivacyRestore {
    gateway: OpenVikingContextGateway,
}

impl OpenVikingPrivacyRestore {
    /// Restore context with privacy preservation
    pub async fn privacy_restore(
        &self,
        caller: &AttestationEvidence,
        context_id: &str,
        privacy_level: PrivacyLevel,
    ) -> Result<PrivacyRestoredContext> {
        // Verify caller and privacy claims
        if !self.verify_caller(caller).await? {
            return Err(GatewayError::AccessDenied {
                reason: "Caller verification failed".to_string(),
            });
        }

        // Check privacy level requirements
        if caller.privacy_posture < privacy_level.required_posture {
            return Err(GatewayError::InsufficientPrivacyPosture {
                required: privacy_level.required_posture,
                actual: caller.privacy_posture,
            });
        }

        // Retrieve and apply privacy transformations
        let context = self.gateway.recall_context(caller, context_id).await?;
        let restored = self.apply_privacy_transforms(context, privacy_level).await?;

        Ok(restored)
    }
}
```

## Configuration

### Environment Variables

```bash
# OpenViking Service Configuration
SERVICE_NAME=openviking-cmem
SERVICE_INSTANCE_ID=openviking-instance-001

# Trust Service
TRUST_SERVICE_URL=http://localhost:8080

# Encrypted Storage
ENCRYPTED_VFS_PATH=/mnt/encrypted
LUKS_VFS_DEVICE=/dev/tdx_vfs

# Policy Configuration
MINIMUM_ASSURANCE_LEVEL=L2
STRICT_MODE=false

# PCCS Server (for collateral fetch)
PCCS_URL=https://localhost:8081/sgx/certification/v4/
```

### Docker Compose Example

```yaml
# filepath: docker-compose.yml
services:
  openviking-cmem:
    image: openviking:latest-tdx
    environment:
      HOST: 0.0.0.0
      PORT: 8010
      SERVICE_NAME: openviking-cmem
      TRUST_SERVICE_URL: http://argus-trust-service:8080
      ENCRYPTED_VFS_PATH: /mnt/encrypted
      MINIMUM_ASSURANCE_LEVEL: L2
      STRICT_MODE: false
      PCCS_URL: https://pccs.example.com/sgx/certification/v4/
    volumes:
      - encrypted_vfs:/mnt/encrypted
      - tsm_socket:/var/run/tsm
    depends_on:
      - argus-trust-service
    devices:
      - /dev/tdx_guest:/dev/tdx_guest
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp:unconfined

  argus-trust-service:
    image: argus-trust-service:latest
    environment:
      HOST: 0.0.0.0
      PORT: 8080
      SGX_QCNL_CONFIG: /etc/sgx_default_qcnl.conf
    volumes:
      - sgx_config:/etc/sgx_default.qcnl.conf

volumes:
  encrypted_vfs:
```

## Verification Flow

```
1. OpenClaw prepares context transfer to OpenViking
         │
         ▼
2. OpenClaw calls local Argus Guard
         │
         ▼
3. Argus Guard fetches service evidence from the provider
         │
         ▼
4. Guard validates quote structure and request binding
         │
         ▼
5. Guard returns normalized claims to the caller
         │
         ▼
6. OpenClaw forwards the verified binding context to OpenViking
         │
         ▼
7. OpenViking trust gate checks binding + TCB policy
         │
         ▼
8. If allow: OpenViking accepts context
   If deny: OpenViking rejects context transfer
```

## API Reference

### Context Operations

| Operation | Route | Description |
|-----------|-------|-------------|
| Observe | `GET /context/{id}/metadata` | Read context metadata (no materialization) |
| Recall | `GET /context/{id}` | Materialize context for processing |
| Commit | `POST /context` | Archive new context with encryption |
| Privacy Restore | `POST /context/{id}/privacy-restore` | Apply privacy transformations |

### Trust Operations

| Operation | Route | Description |
|-----------|-------|-------------|
| Verify Caller | `POST /verify/caller` | Evaluate forwarded caller trust context |
| Get Trust Status | `GET /trust/status` | Get service trust status |

## Manual Service Test

Start service mode:

```bash
python3 openviking_service.py --serve
```

Commit a context using a pre-verified caller binding:

```bash
curl -X POST http://localhost:8010/context \
    -H 'Content-Type: application/json' \
    -H 'X-Binding-Digest: demo-binding-123' \
    -H 'X-TCB-Status: UpToDate' \
    -H 'X-RTMR0: demo-rtmr0' \
    -d '{"context_id":"session-001","data":"hello from openclaw"}'
```

Read back only metadata:

```bash
curl http://localhost:8010/context/session-001/metadata \
    -H 'X-Binding-Digest: demo-binding-123' \
    -H 'X-TCB-Status: UpToDate' \
    -H 'X-RTMR0: demo-rtmr0'
```

## tc-api-assisted Deployment

The simple Python demo is useful for the trust-gate flow, but tc-api-specific
metadata only appears when OpenViking is launched through a tc-api-managed Docker
path.

### Real tc-api + Docker Flow Assets

This directory now includes a concrete deployment path for that flow:

1. `docker-compose.tc-api.yml` starts the local registry, tc-api, and an Argus
    Evidence Provider configured to query tc-api by workload ID. The tc-api
    container starts TruCon and Docktap internally via `start.sh`.
2. `Dockerfile.tc-api-workload` packages `openviking_service.py --serve` as the
    actual service workload.
3. `launch_openviking_via_tc_api.sh` builds that image, pushes it to the host
    local registry at `localhost:5000`, and submits `POST /api/deploy-launch`
    with `metadata.workload_id=openviking-cmem` using the in-network pull
    reference `docker://registry:5000/openviking-cmem:latest`.

Provider-side environment when running next to that workload:

```bash
cd ../../../core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
export ARGUS_SERVICE_ID=openviking-cmem
export TC_API_WORKLOAD_ID=openviking-cmem
export TC_API_URL=http://127.0.0.1:8000
./start_argus.sh start-provider
```

The key requirement is that `ARGUS_SERVICE_ID` and `TC_API_WORKLOAD_ID` match the
workload ID passed to tc-api during `POST /api/deploy-launch`. That lets the
provider query tc-api by workload ID and recover the launched service's image
digest, launch ID, and any available Rekor identifiers.

### End-to-End Steps

1. Start the OpenViking-side control plane and provider:

```bash
cd ../../../adapters/OpenViking/examples
docker-compose -f docker-compose.tc-api.yml up -d registry tc-api argus-provider
```

2. Export one tc-api write credential. Use `TC_API_IDENTITY_TOKEN` for request-body auth or `TC_API_BEARER_TOKEN` for Authorization-header auth:

```bash
export TC_API_IDENTITY_TOKEN='<sigstore token>'
```

If you are using interactive Sigstore login instead of a pre-exported token,
keep the payload on the tc-api CLI path pointed at
`docker://registry:5000/openviking-cmem:latest`. `docker://localhost:5000/...`
passes request validation but fails at pull time because the registry fetch runs
inside the tc-api container.

3. Build and launch the OpenViking workload through tc-api:

```bash
./launch_openviking_via_tc_api.sh
```

4. On the OpenClaw side, point Guard at the OpenViking provider and set the target URI to the launched workload endpoint:

```bash
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-host>:8008
export ARGUS_ALLOW_MOCK_VERIFIER=1
./start_argus.sh start-guard

cd ../../../adapters/OpenClaw/examples
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=http://<openviking-host>:8010
python3 openclaw_agent.py
```

If the launch succeeds, `openclaw_agent.py` should now see the same service name
plus tc-api-backed metadata such as `launch_id`, `image_digest`, and any
available transparency identifiers.

### Validation Status

Verified on 2026-06-29:

- Real interactive tc-api `deploy-launch` completed successfully.
- The launched OpenViking workload answered on `GET /health` at port `8010`.
- Argus provider evidence included tc-api-backed `launch_id`, `image_digest`,
    and `transparency_log_id`.
- OpenClaw completed a real end-to-end HTTP flow against the launched
    OpenViking workload: caller verification, context commit, metadata observe,
    and context recall.

Current boundary:

- The provider-side example can still fall back to a mock quote. Because of
    that, the caller-side Guard used `ARGUS_ALLOW_MOCK_VERIFIER=1` for this
    end-to-end validation. A full real-quote-only Guard validation on this path
    is not yet verified.

## See Also

- [OpenViking Adapter](../README.md) - Main adapter documentation
- [OpenViking CMEM Adapter Docs](../../openspec/specs/openviking-cmem-adapter-docs/spec.md) - Specification
- [OpenClaw Adapter](../OpenClaw/README.md) - Agent integration
- [Trust Gate Specification](../../openspec/specs/openviking-trusted-context-gate/spec.md) - Trust verification
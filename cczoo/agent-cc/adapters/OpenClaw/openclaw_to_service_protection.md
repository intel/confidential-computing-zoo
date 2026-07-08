# OpenClaw Agent Example

This directory contains an example adapter demonstrating how OpenClaw integrates with Agent-CC as an agent runtime.

## Overview

OpenClaw is an agent runtime that uses Agent-CC's core services for attestation-gated operations. OpenClaw runs as a standard process and delegates confidential computing concerns to Argus services:

- **OpenClaw** (caller side): Standard process that makes trust decisions based on Argus verification results
- **OpenViking** (service side): Runs inside a TDVM as the confidential workload being verified
- **Argus Guard**: Verifies OpenViking's TDX attestation evidence on behalf of OpenClaw
- **Argus Provider** (service side): Generates TDX quotes for OpenViking inside the TDVM

This example shows how OpenClaw uses Argus to verify remote service identity and runtime state before exchanging sensitive data.

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

### Step 3: Acquire a Fresh tc-api Launch Token

The tc-api `deploy-launch` path is authenticated. In practice, the Sigstore OIDC
identity token is short-lived, so fetch it immediately before launching the
workload:

```bash
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/core/tc-api
bash ./setup.sh
./venv/bin/python -m tc_api.cli.oidc_verification_code --operation launch --format export
```

That command prints a browser URL. Finish GitHub login, paste the verification
code back into the helper, then export the printed `TC_API_IDENTITY_TOKEN` in
the shell where you will run the e2e script.

### Step 4: Run Full End-to-End Test

```bash
# One-shot real quote path: compose stack + tc-api launch + real Guard + OpenClaw.
cd /home/siyuan/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenClaw/scripts
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
`configs/docker-compose.tc-api.yml` plus `scripts/launch_openviking_via_tc_api.sh` from the
OpenViking directory. The new `run_openclaw_openviking_e2e.sh` wrapper
now stitches that path together with a real-verifier Guard run and the final
OpenClaw verification.

The example calls `POST /ra/v1/verify` on the local Argus Guard and treats the
returned `report_data` as the binding digest for local secret release and
context storage.

## Successful Run Checklist

The validated fresh launch from this repository produced the following concrete
tc-api result:

```bash
curl -fsS http://127.0.0.1:8000/api/launch-result/launch-c17005e
```

```json
{
    "status": "success",
    "validation": "passed",
    "attestation": "trusted",
    "launch_id": "launch-c17005e",
    "log_id": "9253e293-893d-4046-b62b-d93a945f463b",
    "transparencyLog_verify": "success",
    "instance_ids": [
        {
            "container_ID": "b073d524294e",
            "container_Status": "running"
        }
    ],
    "evidence": {
        "workload_id": "openviking-cmem",
        "image_id": "openviking-cmem",
        "image_digest": "sha384:e475081e1c1923296b4b2b4181b47e987e4b383f8c79c054970bfb189fe8acdf15122cca6577981e588dbd84575c2584"
    }
}
```

The validated OpenClaw business flow then completed with these terminal lines:

```text
OpenClaw Agent - Agent-CC Integration Example

[1] Verifying OpenViking through Argus Guard...
        TCB Status: UpToDate
    Service Name: openviking-cmem
    Workload ID: openviking-cmem
    Launch ID: launch-c17005e
    Image Digest: sha384:e475081e1c1923296b4b2b4181b47e987e4b383f8c79c054970bfb189fe8acdf15122cca6577981e588dbd84575c2584
    Trusted Log ID: 9253e293-893d-4046-b62b-d93a945f463b

[2] Creating attestation context...
[6] Calling OpenViking verify endpoint...
        Trusted by OpenViking: True

[7] Committing context to OpenViking...
[8] Observing OpenViking context metadata...
[9] Recalling OpenViking context payload...
        Remote payload: b'OpenClaw to OpenViking end-to-end context payload'

Example completed successfully!
```

This flow surfaced the tc-api trusted-log record identifier
`9253e293-893d-4046-b62b-d93a945f463b`, which the OpenClaw example now prints as
`Trusted Log ID`. The current endpoints still do not expose a separate public
Rekor UUID for this run.

Operational note: tc-api's workload metadata store currently lives at
`/dev/shm/docktap/container_map.db` inside the tc-api container. Restarting the
tc-api container intentionally clears that tmpfs-backed state; a fresh `deploy-launch` then
re-populates the workload row automatically.

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

## Manual Split Deployment

The `Quick Start` above is the authoritative path for the validated fresh
`deploy-launch` flow, including concrete success output.

Use the steps below only if you want to run the two sides manually instead of
using `scripts/run_openclaw_openviking_e2e.sh`.

### OpenClaw Side

```bash
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-provider-host>:8008
./start_argus.sh start-guard

cd ../../../adapters/OpenClaw/scripts
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=https://<openviking-service-host>
python3 openclaw_agent.py
```

### OpenViking Side

```bash
cd ../../../core/argus
export ARGUS_WORKLOAD_IDENTITY=openviking-cmem
./start_argus.sh start-provider
```

When you use this manual split deployment instead of the tc-api launch path,
tc-api-specific fields such as `image_digest`, `launch_id`, and `Trusted Log ID`
will be empty unless tc-api is also tracking the workload.

## See Also

- [OpenClaw Adapter](../README.md) - Main adapter documentation
- [Argus Verifier](../../core/argus/README.md) - TDX quote verification
- [TC-API Service](../../core/tc-api/README.md) - Build-to-runtime trust
- [Trust Service](../../core/trust-service/README.md) - Attestation support

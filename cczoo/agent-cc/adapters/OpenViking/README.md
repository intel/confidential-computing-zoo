# OpenViking Service Example

This directory contains an example adapter demonstrating how OpenViking integrates with Agent-CC as a confidential memory service.

## Overview

OpenViking is an open-source Context Database designed specifically for AI Agents. It provides attestation-gated context storage and retrieval. This example shows how OpenViking uses Agent-CC's core services for trusted context transfer.

## Running Examples

For complete end-to-end testing, see [OpenClaw to service protection](../OpenClaw/openclaw_to_service_protection.md).

## Run OpenViking Service Only

For a quick in-memory demo without full attestation:

```bash
python3 cczoo/agent-cc/adapters/OpenViking/scripts/openviking_service.py
```

Or start the HTTP gateway for manual testing:

```bash
python3 openviking_service.py --serve
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

The adapter provides these deployment assets:

1. `configs/docker-compose.tc-api.yml` starts the local registry, tc-api, and an Argus
    Evidence Provider configured to query tc-api by workload ID. The tc-api
    container starts TruCon and Docktap internally via `start.sh`.
2. `configs/Dockerfile.tc-api-workload` packages `openviking_service.py --serve` as the
    actual service workload.
3. `scripts/launch_openviking.sh` builds that image, pushes it to the local
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

```bash
cd cczoo/agent-cc/adapters/OpenViking/scripts
OPENVIKING_USE_LUKS=0 ./launch_openviking.sh
```

This local-test mode stores data in the container layer and does not provide
encryption at rest. The launcher obtains a TC-API identity interactively when
no token is exported. Do not use this mode for sensitive data.

### Encrypted-at-Rest Storage (Deferred)

`openviking_service.py` can persist contexts under `OPENVIKING_DATA_DIR`, but
TC-API intentionally rejects arbitrary Docker command overrides. A structured,
path-validated LUKS bind-mount API has not been implemented yet. The launcher
therefore fails closed when `OPENVIKING_USE_LUKS=1` (the default). For
non-production testing only, set `OPENVIKING_USE_LUKS=0`; this uses
container-local storage and does not provide encryption at rest. Do not pass
`dockercmd` or claim encrypted persistence until the structured mount support
is available.

4. On the OpenClaw side, point Guard at the OpenViking provider and set the target URI to the launched workload endpoint:

```bash
cd ../../../core/argus
export EVIDENCE_ENDPOINT=http://<openviking-host>:8008
export ARGUS_ALLOW_MOCK_VERIFIER=1
./start_argus.sh start-guard

cd ../../../adapters/OpenClaw/scripts
export TARGET_SERVICE_NAME=openviking-cmem
export TARGET_URI=http://<openviking-host>:8010
python3 openclaw_agent.py
```

If the launch succeeds, `openclaw_agent.py` should now see the same service name
plus tc-api-backed metadata such as `launch_id`, `image_digest`, and any
available transparency identifiers.

## See Also

- [OpenViking Adapter](../README.md) - Main adapter documentation
- [OpenViking CMEM Adapter Docs](../../openspec/specs/openviking-cmem-adapter-docs/spec.md) - Specification
- [OpenClaw Adapter](../OpenClaw/openclaw_to_service_protection.md) - Agent integration

# OpenViking Service Example

This directory contains an example adapter demonstrating how OpenViking integrates with Agent-CC as a confidential memory service.

## Overview

OpenViking is an open-source Context Database designed specifically for AI Agents. It provides attestation-gated context storage and retrieval. This example shows how OpenViking uses Agent-CC's core services for trusted context transfer.

## Running Examples

For complete end-to-end testing, see [OpenClaw to service protection](../../OpenClaw/openclaw_to_service_protection.md)

## Run OpenViking Service Only

For a quick in-memory demo without full attestation:

```bash
cd <work_dir>/confidential-computing-zoo/cczoo/agent-cc/adapters/OpenViking/examples
python3 openviking_service.py
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

### LUKS-Backed Persistent Storage (Recommended)

By default, `openviking_service.py` now persists committed contexts to
`OPENVIKING_DATA_DIR` (default `/mnt/encrypted/openviking`).
For TDX disk-at-rest protection, mount a LUKS filesystem on the host and let
`launch_openviking_via_tc_api.sh` bind-mount it into the workload container.

1. Create and mount encrypted storage on the OpenViking host:

```bash
cd ../../../../openclaw-cc/luks_tools
./create_encrypted_vfs.sh 10G /root/vfs-openviking.img
# Record the printed LOOP_DEVICE, then mount it.
./mount_encrypted_vfs.sh <LOOP_DEVICE> format openviking_luks /home/encrypted_storage
```

2. Launch OpenViking with LUKS enabled (default is enabled):

```bash
cd ../agent-cc/adapters/OpenViking/scripts
export OPENVIKING_USE_LUKS=1
export OPENVIKING_LUKS_MOUNT_ROOT=/home/encrypted_storage
export OPENVIKING_LUKS_SUBDIR=openviking
export OPENVIKING_CONTAINER_DATA_DIR=/mnt/encrypted/openviking
./launch_openviking_via_tc_api.sh
```

If `OPENVIKING_USE_LUKS=1`, the launcher requires
`OPENVIKING_LUKS_MOUNT_ROOT` to be an active mountpoint; otherwise it fails
fast to avoid writing plaintext data to an unprotected path.

3. Optional: disable LUKS enforcement for quick local testing:

```bash
export OPENVIKING_USE_LUKS=0
./launch_openviking_via_tc_api.sh
```

### Real Persistence: Env Vars and Configuration Mechanism

OpenViking disk persistence is enabled by an end-to-end launch path, not by
in-memory demo settings alone:

1. Host launcher `launch_openviking_via_tc_api.sh` reads LUKS/storage env vars.
2. The launcher builds `dockercmd` and sends it in tc-api `POST /api/deploy-launch`.
3. At container start, `dockercmd` injects both:
    - `-e OPENVIKING_DATA_DIR=<container path>`
    - `-v <host path>:<container path>`
4. `openviking_service.py` reads `OPENVIKING_DATA_DIR` and persists contexts to
    `<OPENVIKING_DATA_DIR>/contexts/`.

Variable reference by scope:

| Variable | Scope | Default | Purpose |
|---|---|---|---|
| `OPENVIKING_USE_LUKS` | host launcher | `1` | Enforce LUKS mountpoint checks. If `1`, launch fails when mount is missing. |
| `OPENVIKING_LUKS_MOUNT_ROOT` | host launcher | `/home/encrypted_storage` | Host LUKS mount root (must be an active mountpoint). |
| `OPENVIKING_LUKS_SUBDIR` | host launcher | `openviking` | Subdirectory under mount root for OpenViking data. |
| `OPENVIKING_CONTAINER_DATA_DIR` | host launcher | `/mnt/encrypted/openviking` | Container data directory used for both env injection and bind-mount target. |
| `OPENVIKING_DATA_DIR` | in-container service | `/mnt/encrypted/openviking` | Runtime data directory read by `openviking_service.py`. |

Mental model:
`OPENVIKING_* (host)` -> `dockercmd` -> `OPENVIKING_DATA_DIR (container)` ->
service writes `${OPENVIKING_DATA_DIR}/contexts/*.json`.

Quick verification:

```bash
# 1) Check in-container env var
docker exec <openviking_container> printenv OPENVIKING_DATA_DIR

# 2) Check persisted files in container
docker exec <openviking_container> ls -l ${OPENVIKING_CONTAINER_DATA_DIR}/contexts

# 3) Check matching host path
ls -l ${OPENVIKING_LUKS_MOUNT_ROOT}/${OPENVIKING_LUKS_SUBDIR}/contexts
```

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

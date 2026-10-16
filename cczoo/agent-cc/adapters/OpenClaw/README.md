# OpenClaw Adapter

The OpenClaw Adapter provides container-based integration paths for deploying OpenClaw workloads within Intel TDX trusted execution environments, supporting tool sandboxing and supply-chain integrity verification.

> **Looking for the recommended baseline deployment?**
> For native TDVM deployment with local Ollama and encrypted LUKS storage, see the [OpenClaw Confidential Computing Best Practices Guide](../../best-practices/README.md) ([中文](../../best-practices/README_CN.md)) and the [OpenClaw-CC Native Deployment Guide](../../../openclaw-cc/README.md).

This adapter documents two container-based deployment workflows:
1. **Container Sandbox Mode**: Running OpenClaw Gateway with isolated tool containers from `openclaw-sandbox:bookworm-slim`.
2. **TC-API Build-to-Runtime Lifecycle**: Building encrypted images with SBOM, signing with Sigstore/Cosign, and enforcing hardware attestation before container launch.

---

## Deployment Modes Overview

| Mode | Trust Boundary | Key Capabilities | Best For |
| --- | --- | --- | --- |
| **Native TDVM** | Whole TDVM | Direct execution, hardware memory encryption, native LUKS state volume. | Recommended production baseline. |
| **Container Sandbox** | Single TDVM (Docker inside TD) | Gateway orchestrates tools inside isolated temporary containers. | Workloads executing untrusted third-party tools or arbitrary shell commands. |
| **TC-API Lifecycle** | Single TDVM (Docker + TC-API) | Encrypted container image, SBOM generation, Sigstore signing, attestation-gated launch. | Enterprise CI/CD pipelines requiring verifiable build-to-runtime provenance. |

*Note: Running Docker containers inside a TDVM shares the single TD trust boundary. Containers inside a TD do not form separate hardware TEEs unless deployed with Confidential Containers (CoCo) / Kata TDX.*

---

## Workflow 1: Container Sandbox Mode (Gateway + Sandboxed Tools)

In this mode, OpenClaw Gateway runs inside a Docker container within the TDVM. When the agent executes tools or shell scripts, it spawns short-lived `openclaw-sandbox:bookworm-slim` containers to isolate tool execution from the gateway.

### 1. Build Gateway and Sandbox Images

Navigate to the scripts directory and configure the environment:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts

# Builds openclaw-sbx:latest and openclaw-sandbox:bookworm-slim.
# Use loopback when the gateway should only be reachable inside the TD.
bash run-sbx.sh --bind loopback
```

Optional environment variables are `OPENCLAW_GATEWAY_PORT`, `OPENCLAW_GATEWAY_TOKEN`, `OPENCLAW_CONFIG_VOLUME`, and `OPENCLAW_WORKSPACE_VOLUME`. The gateway image is `openclaw-sbx:latest`. Configuration and workspace are stored in the Docker volumes `openclaw-config` and `openclaw-workspace`.

### 2. Configure OpenClaw Gateway

Onboard OpenClaw interactively or mount configuration into the config volume:

```bash
docker run --rm -it --user node \
  -v openclaw-config:/home/node/.openclaw \
  -v openclaw-workspace:/home/node/.openclaw/workspace \
  --entrypoint node openclaw-sbx:latest /app/dist/index.js onboard --mode local --no-install-daemon
```

Bind host Ollama to `docker0` with `ollama-td.sh setup docker`, then configure the provider in the `openclaw-config` volume at `/home/node/.openclaw/openclaw.json`:

```json
{
  "models": {
    "providers": {
      "local-ollama": {
        "baseUrl": "http://host.docker.internal:11434/v1",
        "apiKey": "ollama",
        "api": "openai-completions",
        "models": ["qwen2.5:7b"]
      }
    },
    "default": "local-ollama/qwen2.5:7b"
  }
}
```

### 3. Verify Sandbox Execution

1. `run-sbx.sh` prints the gateway token. Open `http://127.0.0.1:18789/` and enter the token in the UI. Do not put the token in the URL.
2. When a task requires tool or code execution, the gateway launches an ephemeral `openclaw-sandbox:bookworm-slim` container.

---

## Workflow 2: Trusted Build, Publish & Launch via TC-API

TC-API provides a verifiable control plane for building encrypted images, generating SBOMs, signing artifacts, and gating container deployment on TDX hardware attestation.

### Prerequisites

- An Intel TDX TDVM with `/dev/tdx_guest` available.
- Docker daemon running inside the TDVM.
- TC-API, Trust Service, and local KBS dependencies running. Refer to the [TC-API Quick Start](../../core/tc_api/README.md) and [trust_service.sh](../../core/trust-service/trust_service.sh).
- Sigstore/OIDC identity and Docker registry credentials configured in TC-API `.env`.

### 1. Start TC-API Control Plane

Start TC-API inside the TDVM:

```bash
cd cczoo/agent-cc/core/tc_api
./start.sh restart dev
```

### 2. Build, Publish, and Attested Launch Flow

Use `create_luks`, `mount_luks`, `build`, `publish`, and `deploy`. Request fields are listed at `http://localhost:8000/docs` and in the [TC-API README](../../core/tc_api/README.md). Publishing also requires registry settings in `.env`.

```bash
cd cczoo/agent-cc/core/tc_api
source venv/bin/activate

venv/bin/python -m tc_api.cli.client --base-url http://localhost:8000 \
  create_luks --payload-json '{"user_id":"<sigstore account>","vfs_path":"<luks file>","vfs_size":"<size>","passwd":"<luks key file>"}'
```

### 3. Inspect Trust Evidence

Query TC-API verification endpoints to validate end-to-end evidence:

- `GET /api/build-result/{build_id}`: Image digest, SBOM location, and build-time trust status.
- `GET /api/publish-result/{build_id}`: Cosign signatures and registry publication proof.
- `GET /api/launch-result/{launch_id}`: TDX Quote validation results and container launch status.
- `GET /api/transparency-log/{log_id}`: Signed, immutable audit records in Rekor.

For comprehensive API request specifications, see the [TC-API Documentation](../../core/tc_api/README.md).

---

## Security Boundaries & Operational Considerations

1. **Docker Daemon Boundary**: The Docker daemon running inside the TDVM controls container execution. Access to `/var/run/docker.sock` must be restricted to trusted processes, as access to the Docker socket allows full root control over the TDVM.
2. **Container vs. Hardware Boundary**: Containers inside a TD share the same kernel and TDX TCB. Containers provide process namespace isolation, while the TDVM provides hardware memory encryption against the external host.
3. **Secret Hygiene**: Never store API tokens or Sigstore signing secrets in Docker images or container layers. Passwords and keys must be injected at runtime or mounted from an encrypted volume.

---

## Related References

- [OpenClaw Best Practices Guide](../../best-practices/README.md) - Production architecture and deployment recommendations
- [TC-API Control Plane](../../core/tc_api/README.md) - Complete documentation of the build/publish/launch API
- [Trusted Log (TLog)](../../core/tlog/README.md) - Immutable signed audit logging
- [Trust Service script](../../core/trust-service/trust_service.sh) - Remote attestation and key broker helper

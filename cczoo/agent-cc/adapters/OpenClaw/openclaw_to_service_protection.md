# OpenClaw Adapter

The OpenClaw adapter documents container-based deployment, tool sandboxing,
and integration with trusted services on Intel TDX.

> **Recommended production baseline:** For native TDVM deployment with local
> Ollama and encrypted LUKS storage, see the
> [OpenClaw Confidential Computing Best Practices Guide](../../best-practices/README.md)
> and the [OpenClaw-CC Native Deployment Guide](../../../openclaw-cc/README.md).

## Deployment modes

| Mode | Trust boundary | Capabilities | Intended use |
| --- | --- | --- | --- |
| Native TDVM | Whole TDVM | TDX memory protection and native LUKS state storage | Recommended production baseline |
| Container sandbox | Single TDVM; Docker isolates tool containers | Short-lived sandbox containers for tool execution | Untrusted tools or shell workloads |
| TC-API lifecycle | Single TDVM; Docker plus TC-API | Build/publish evidence and attestation-gated launch | Verifiable build-to-runtime workflows |

Containers inside one TDVM share its kernel and hardware trust boundary. They
are not separate hardware TEEs unless deployed with Confidential Containers
(CoCo) or Kata TDX.

## Container sandbox

From the repository root, build and start the gateway with loopback-only host
ports:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
bash run-sbx.sh --bind loopback
```

The script uses persistent Docker volumes for gateway configuration and
workspace. It generates a gateway token when one is not supplied; enter that
token in the local UI and do not put it in a URL or source file. The default
container name is `openclaw-gateway`.

The gateway can execute tools in short-lived `openclaw-sandbox:bookworm-slim`
containers. Access to the Docker socket is effectively root access to the TDVM;
only grant it to a trusted gateway process.

## Configure Ollama as the primary model

This connector configures OpenClaw to call a local Ollama server. It does not
perform Argus verification or make model access attestation-gated. Keep the
Ollama model files on the active LUKS mount:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
./run_ollama_luks.sh pull llama3.2
```

For the gateway container to reach the host service without listening on every
host interface, bind Ollama to the Docker bridge address rather than
`0.0.0.0`:

```bash
DOCKER0_IP="$(ip -4 -o addr show dev docker0 | awk 'NR == 1 { split($4, a, "/"); print a[1] }')"
if [[ -z "$DOCKER0_IP" ]]; then
  echo "docker0 has no IPv4 address" >&2
  exit 1
fi
OLLAMA_HOST="${DOCKER0_IP}:11434" ./run_ollama_luks.sh serve
```

Keep the `serve` command running in a separate terminal. In another terminal,
configure the running gateway:

```bash
cd cczoo/agent-cc/adapters/OpenClaw/scripts
export OPENCLAW_CONTAINER=openclaw-gateway
export OLLAMA_BASE_URL="http://${DOCKER0_IP}:11434"
export OLLAMA_CONTAINER_BASE_URL=http://host.docker.internal:11434
export OLLAMA_MODEL=llama3.2
./connect_openclaw_ollama.sh
```

`run-sbx.sh` adds the `host.docker.internal:host-gateway` mapping. If you use a
different gateway container or Docker network, set `OPENCLAW_CONTAINER` and
`OLLAMA_CONTAINER_BASE_URL` to the actual reachable values. Binding Ollama to
`docker0` limits exposure to that bridge, but other trusted containers on the
bridge may still reach its unauthenticated API. Use firewall or dedicated
network controls where needed.

The connector checks Ollama readiness, verifies that the model is installed,
tests connectivity from the gateway, updates the provider configuration, and
restarts OpenClaw. `run_ollama_luks.sh` requires an active LUKS mount and stores
models below it; do not substitute plain `ollama pull` or `ollama serve` when
encrypted model storage is required.

## TC-API build-to-runtime lifecycle

TC-API provides build, publish, and launch endpoints for workflows that need
signed artifacts, SBOMs, and runtime evidence. See the
[TC-API Quick Start](../../core/tc_api/README.md) for prerequisites and API
details. The TC-API launch interface must remain fixed and allowlisted; do not
pass caller-controlled Docker command strings.

## OpenViking integration status

The OpenViking adapter's official-image launcher currently fails closed because
the TC-API launch path uses host networking and lacks structured
loopback-only-port and validated configuration/data-mount options. The previous
one-click end-to-end workflow is therefore unavailable; see the
[OpenViking adapter guide](../OpenViking/README.md) for the current limitation.
Do not treat `connect_openclaw_openviking.sh` as a workload launcher; it only
connects to services that are already running.

## Security boundaries

1. Access to `/var/run/docker.sock` can control the TDVM's Docker daemon and
   must be restricted to trusted processes.
2. Containers inside a TD share its kernel and TDX trust boundary; container
   isolation does not replace least privilege, sandboxing, or policy controls.
3. Never store API tokens or signing secrets in images, source files, command
   history, or logs. Inject short-lived credentials at runtime or keep them in
   an encrypted secret store.
4. Bind local services to loopback or a dedicated trusted network. Do not
   assume a container or host-network launch is loopback-only.

## Related references

- [OpenClaw container protection](openclaw_container_protection.md)
- [OpenViking adapter](../OpenViking/README.md)
- [Ollama adapter](../Ollama/README.md)
- [Argus](../../core/argus/README.md)
- [TC-API](../../core/tc_api/README.md)
- [Trusted Log (TLog)](../../core/tlog/README.md)
- [OpenClaw best practices](../../best-practices/README.md)

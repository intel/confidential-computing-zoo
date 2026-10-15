# OpenViking with workload attestation

This adapter supplies the OpenViking image and configuration for the
`openviking-cmem` workload. Deployment is controlled by the shared
[workload attestation runtime](../../core/spire/workload/README.md). Attestation
checks the current listener and authenticated lifecycle history before SPIRE
Server's CA issues the workload X.509-SVID. NGINX is managed inside the TDX
guest, outside the application container; it binds use of that identity to
the registered backend and provides the NGINX service endpoint. Requests require
mTLS, an allowed client SPIFFE ID and OpenViking's API-key authorization.

## Image

From `cczoo/agent-cc/adapters/OpenViking`, build the thin image from an approved
official base digest:

```bash
export OPENVIKING_BASE='ghcr.io/volcengine/openviking@sha256:<approved-base-digest>'
export OPENVIKING_IMAGE='registry:5000/openviking:<approved-release>'
docker build --build-arg OPENVIKING_BASE="$OPENVIKING_BASE" \
  -f configs/Dockerfile.openviking -t "$OPENVIKING_IMAGE" .
docker push "$OPENVIKING_IMAGE"
docker image inspect "$OPENVIKING_IMAGE" --format '{{.Id}}'
```

[Dockerfile.openviking](configs/Dockerfile.openviking) fixes the entrypoint to
`openviking-server` and clears the inherited command. The resulting image
config ID is the `sha256:` value required by `approved.image_config_digest`;
the registry manifest/base-image digest is a different value.

## Application configuration

Create configuration and writable data in separate paths on the trusted TDX
guest:

```bash
sudo install -d -m 0700 /srv/openviking /srv/openviking/data
sudo install -m 0600 configs/ov.conf.example /srv/openviking/ov.conf
```

Fill in the root API key, embedding and VLM providers/models/endpoints/keys
in [ov.conf.example](configs/ov.conf.example), including the output dimension
for the chosen embedding model. Ensure the application account can write its
data directory. Review the completed file and record its exact SHA-256 as
`sha256:<hex>` in `approved.config_digest` in the deployment configuration.

The example deployment uses these matching settings:

| OpenViking / guest setting | Workload deployment setting |
|---|---|
| `server.host = 127.0.0.1` | Business listener is reachable through NGINX in the same network namespace |
| `server.port = 1933` | `workload.listen_port = 1933` |
| Host `/srv/openviking/ov.conf` | `config_host_path`; mounted read-only at `config_path = /etc/openviking/ov.conf` |
| `OPENVIKING_CONFIG_FILE=/etc/openviking/ov.conf` | `config_env = OPENVIKING_CONFIG_FILE`, with the same path in `workload.environment` |
| `storage.workspace = /var/lib/openviking` | `data_path = /var/lib/openviking`; writable host directory is `data_host_path = /srv/openviking/data` |
| NGINX TLS port `1943` | `tls_port = 1943`, `published_port = 1943` |

The example explicitly lists these OpenViking field checks in
`workload.config_json_checks`. Its environment map also sets
`PYTHONDONTWRITEBYTECODE=1` and `OPENVIKING_WITH_BOT=0`. Shared launch and
attestation code uses those declarations without recognizing OpenViking
field names.

The application container uses read-only rootfs, no capabilities, a private
bridge network namespace and limited `/tmp`. Only the NGINX TLS port is
published. The application receives no TDX device, SPIRE socket or SVID key.

## Deployment and service access

Follow the [deployment guide](../../core/spire/workload/README.md) to build
and install the attestation components, configure Trustee policy and SPIRE
entries, and expose `ARGUS_WORKLOAD_CONFIG` to TC API. The TC API workload
attestation profile is `nginx-spiffe`; it derives mounts and
environment from the protected configuration and rejects arbitrary command
overrides.

Use `workload.py launch`, `register`, `preflight` and `start` in that guide.
Registration must resolve one actual listener and its approved executable,
image/configuration digests and current launch. Use `resume-launch` to
reconcile an interrupted operation with the same saved ID.

Clients connect to `https://<guest>:1943` with a valid SVID, key and trust
bundle. The client SPIFFE ID must be present in the exact allowlist and the
client must authenticate the configured target SPIFFE ID. OpenViking's
API-key authorization remains active. Use an OpenViking user API key for the
client and keep the root API key on the server. The runtime's `verify` command
checks current identity delivery and an authorized business request using supplied
client credentials. The example's `business_headers` maps `X-API-Key` to
`OPENVIKING_API_KEY`; explicitly preserve that variable when running `verify`
with sudo. A client-side direct probe needs
`-header-env X-API-Key=OPENVIKING_API_KEY`. No API-key environment variable is
read implicitly. Successful mTLS authenticates communication identities;
Helper monitors the registered process, configuration and listener while
NGINX serves requests.
Ordinary requests do not perform a new remote attestation.

Manage stop/replacement through the authentication lifecycle and existing
TC API/Docktap path. A replacement PID instance requires registration and
admission again, even if its logical SPIFFE ID is unchanged. SVID updates on
the same valid subscription reuse admission; a new subscription requires
fresh evidence. See the [trust boundaries](../../core/spire/workload/ARCHITECTURE.md)
for credential cleanup and the limits of SVID renewal and local monitoring.

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
`openviking-server`, clears the inherited command and runs the application as
UID/GID `10001:10001`. The shared launcher uses the image's `USER`; no
application-specific user handling is needed in TC API.
The resulting image config ID is the `sha256:` value required by
`approved.image_config_digest`; the registry manifest/base-image digest is
a different value. Rebuild and approve the new image config ID after changing
the image, including its user, environment or health check.

The explicit Docker health check reads `server.port` from the file named by
`OPENVIKING_CONFIG_FILE` and calls `http://127.0.0.1:<port>/health` without an
API key. Missing/unreadable configuration, an invalid port or a failed HTTP
check makes the container unhealthy. This checks application liveness, not
workload attestation, API-key authorization or embedding/VLM availability.
It does not replace the separate Helper/NGINX readiness check.

## Application configuration

Create configuration and writable data in separate paths on the trusted TDX
guest:

```bash
sudo install -d -o root -g root -m 0700 /srv/openviking
sudo install -d -o 10001 -g 10001 -m 0700 /srv/openviking/data
sudo install -o root -g 10001 -m 0640 configs/ov.conf.example /srv/openviking/ov.conf
```

Fill in the root API key, embedding and VLM providers/models/endpoints/keys
in `/srv/openviking/ov.conf`, based on [ov.conf.example](configs/ov.conf.example),
including the output dimension for the chosen embedding model. Preserve root
ownership and group `10001` read access (`0640`); the application must not own
or modify this read-only configuration. The data directory must be writable
by the container's UID/GID `10001:10001`. These ownership examples assume
Docker without user-namespace remapping; use the corresponding host-mapped
IDs when remapping is enabled. Review the completed file and record its exact SHA-256 as
`sha256:<hex>` in `approved.config_digest` in the deployment configuration.

For an existing workspace, stop the workload and migrate its data-file ownership
to the application account before switching images. Creating the data directory
does not change the ownership of files already inside it.

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
The image sets `HOME=/var/lib/openviking` and
`XDG_CACHE_HOME=/var/lib/openviking/.cache`, so user state and cache use the
writable data mount; `TMPDIR=/tmp` uses the bounded temporary mount and
`PYTHONDONTWRITEBYTECODE=1` avoids writes beside installed Python modules.
If `data_path` changes, explicitly update `HOME` and `XDG_CACHE_HOME` in
`workload.environment` to paths on that writable mount. Host-managed NGINX,
Provider and Helper retain their separate service permissions; changing the
application's user does not change their accounts or network-namespace entry.

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
Set `approved.executable` to the actual listener process's resolved
`/proc/<pid>/exe` path observed on the trusted guest. Do not assume a Python
minor version from an example; an interpreter upgrade requires reviewing
that executable path together with the new image config ID.

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

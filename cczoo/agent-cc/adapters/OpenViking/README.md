# OpenViking with workload attestation

This adapter deploys the official OpenViking server as the `openviking-cmem`
workload and uses the shared workload-attestation runtime to authenticate
service access.

## Security model and status

The supported deployment uses the TC-API `nginx-spiffe` workload profile.
Runtime settings come from a root-owned operator configuration, not request
supplied Docker arguments. The profile uses a Docker bridge network, a
read-only root filesystem and configuration mount, a separate writable data
mount, no added capabilities, and a limited `/tmp`. The application container
does not receive TDX devices, SPIRE sockets, or SVID private keys.

Host-managed NGINX presents the workload's X.509-SVID and requires mTLS,
an exact client SPIFFE-ID allowlist, and OpenViking API-key authorization.
Docker publishes the configured TLS port on host interfaces; it is not
loopback-only. Restrict that port to trusted clients with network/firewall
controls. Ordinary requests use the established mTLS identity and do not
perform a new remote attestation.

The legacy [`scripts/launch_openviking.sh`](scripts/launch_openviking.sh)
generic launch path remains fail-closed. Use the workload-attestation
deployment described below; do not bypass the guard with arbitrary Docker
command overrides.

## Build a pinned image

Choose a tested official release and resolve its immutable base-image digest:

```bash
cd cczoo/agent-cc/adapters/OpenViking
export OPENVIKING_BASE='ghcr.io/volcengine/openviking@sha256:<approved-base-digest>'
export OPENVIKING_IMAGE='registry:5000/openviking:<approved-release>'
docker build --build-arg OPENVIKING_BASE="$OPENVIKING_BASE" \
  -f configs/Dockerfile.openviking -t "$OPENVIKING_IMAGE" .
docker push "$OPENVIKING_IMAGE"
docker image inspect "$OPENVIKING_IMAGE" --format '{{.Id}}'
```

The Docker image config ID (`.Id`) is the value required by
`approved.image_config_digest`; it is distinct from the registry manifest and
base-image digests. The wrapper Dockerfile fixes the server entrypoint and
clears the inherited command.

## Prepare application configuration and encrypted data

Mount the dedicated LUKS filesystem at `/srv/openviking` before creating these
paths. The TC-API profile validates configured paths and keeps mounts
structured, but it does not verify the backing filesystem type. Confirm the
mount source is the intended dm-crypt device and keep the mount active for the
workload's lifetime:

```bash
findmnt --mountpoint /srv/openviking >/dev/null || {
  echo "/srv/openviking must be the active LUKS mount point" >&2
  exit 1
}
findmnt --noheadings --output SOURCE,FSTYPE --mountpoint /srv/openviking
sudo install -d -m 0700 /srv/openviking/data
sudo install -m 0600 configs/ov.conf.example /srv/openviking/ov.conf
```

Replace every placeholder in `ov.conf.example`, including the root API key,
embedding/VLM providers, endpoints, model names, and API keys. Keep the root
key on the server; clients must use a dedicated User API Key. Do not commit the
completed file or bake it into an image. Record the exact configuration
SHA-256 as `approved.config_digest`.

The example deployment checks the application's configuration against its
declared listener and data paths:

| OpenViking setting | Workload setting |
|---|---|
| `server.host = 127.0.0.1` | NGINX shares the workload network namespace |
| `server.port = 1933` | `workload.listen_port = 1933` |
| Host `ov.conf` | Read-only mount at `/etc/openviking/ov.conf` |
| `OPENVIKING_CONFIG_FILE` | Must match `workload.config_path` |
| `storage.workspace = /var/lib/openviking` | Writable host path is `/srv/openviking/data` |
| NGINX TLS port `1943` | Configured `tls_port` and `published_port` |

These configuration checks verify declared JSON fields and types; they do not
prove that application code continues to consume the file. The runtime
supervisor separately monitors the registered process, configuration digest,
and listener.

## Deploy and verify

Follow the [workload-attestation deployment guide](../../core/spire/workload/README.md)
to build/install the runtime and configure Trustee, SPIRE, and TC-API. Its
strict root-owned `environment.json` must contain the approved image config ID,
configuration digest, TDX measurements, exact client SPIFFE ID(s), and the
OpenViking host/container paths.

Set TC-API's `ARGUS_WORKLOAD_CONFIG` to the protected workload export. If
TC-API runs in a container, mount that file read-only and make
`config_host_path` and `data_host_path` visible at the same paths used by the
Docker host. The request selects `workload_attestation_profile=nginx-spiffe`;
the profile derives Docker options and environment from the protected export
and rejects arbitrary command overrides.

On the guest, use the guide's lifecycle commands:

```bash
sudo python3 /opt/argus-workload/scripts/workload.py launch \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py register \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py preflight \
  --config /etc/argus-workload/environment.json
sudo python3 /opt/argus-workload/scripts/workload.py start \
  --config /etc/argus-workload/environment.json
sudo --preserve-env=OPENVIKING_API_KEY \
  python3 /opt/argus-workload/scripts/workload.py verify \
  --config /etc/argus-workload/environment.json
```

Clients connect to `https://<guest>:1943` using a valid SVID, private key,
trust bundle, an allowlisted SPIFFE ID, and an OpenViking User API Key. Keep
the Root API Key on the server. Use `resume-launch` with the original launch
ID after an interrupted operation; do not create a replacement until the
existing lifecycle state has been reconciled.

The shared runtime supports explicit mTLS clients and API-key headers. Direct
OpenClaw plugin provisioning for this mTLS endpoint is not performed by the
legacy connector script; configure a client-side credential integration
before routing OpenClaw traffic to it.

## References

- [Workload-attestation deployment guide](../../core/spire/workload/README.md)
- [Workload-attestation architecture](../../core/spire/workload/ARCHITECTURE.md)
- [TC-API workload profile](../../core/tc_api/README.md#workload-attestation-profile)
- [OpenClaw adapter guide](../OpenClaw/openclaw_to_service_protection.md)

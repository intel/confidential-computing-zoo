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

Replace every placeholder in `ov.conf.example`, including the root API key,
embedding/VLM providers, endpoints, model names, and API keys. Keep the root
key on the server; clients must use a dedicated User API Key. Do not commit the
completed file or bake it into an image. Record the exact configuration
SHA-256 as `approved.config_digest`.

The example deployment checks the application's configuration against its
declared listener and data paths and uses these matching settings:

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

The application container uses a read-only rootfs, no capabilities, Docker
bridge networking and limited `/tmp`. Only the NGINX TLS port is published.
The application receives no TDX device, SPIRE socket or SVID key.
The image sets `HOME=/var/lib/openviking` and
`XDG_CACHE_HOME=/var/lib/openviking/.cache`, so user state and cache use the
writable data mount; `TMPDIR=/tmp` uses the bounded temporary mount and
`PYTHONDONTWRITEBYTECODE=1` avoids writes beside installed Python modules.
If `data_path` changes, explicitly update `HOME` and `XDG_CACHE_HOME` in
`workload.environment` to paths on that writable mount. Host-managed NGINX,
Provider and Helper retain their separate service permissions; changing the
application's user does not change their accounts or network-namespace entry.

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

Use `workload.py launch`, `register`, `preflight` and `start` in that guide.
Registration must resolve one actual listener and its approved executable,
image/configuration digests and current launch. Use `resume-launch` to
reconcile an interrupted operation with the same saved ID.
Set `approved.executable` to the actual listener process's resolved
`/proc/<pid>/exe` path observed on the trusted guest. Do not assume a Python
minor version from an example; an interpreter upgrade requires reviewing
that executable path together with the new image config ID.

```bash
sudo --preserve-env=TC_API_BEARER_TOKEN,TC_API_IDENTITY_TOKEN \
  python3 /opt/argus-workload/scripts/workload.py launch \
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

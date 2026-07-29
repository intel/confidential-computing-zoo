# OpenViking Adapter

This adapter is intended to deploy the official OpenViking server as the
`openviking-cmem` workload and connect it to OpenClaw through the official
plugin.

## Current deployment status

The launcher deliberately fails closed. The current TC-API launch path runs
workloads with host networking and does not provide structured options for
loopback-only port exposure or validated configuration/data mounts. Therefore,
the adapter cannot currently guarantee that OpenViking is isolated to
`127.0.0.1` or that its state is stored on the intended encrypted volume.

Do not bypass this check with arbitrary Docker command overrides. Support can
be enabled after TC-API provides an allowlisted loopback-port interface and a
path-validated mount API for configuration and LUKS-backed state.

The Compose stack binds its published control-plane ports to `127.0.0.1`, but
TC-API and the evidence provider require privileged TDX access, and TC-API
mounts the host Docker socket. Run this development stack only on a trusted
host.

## Prepare a pinned official image

The wrapper image uses the official OpenViking image as its base. Select a
tested release and resolve it to an immutable digest:

```bash
docker pull "ghcr.io/volcengine/openviking:<tested-version>"
docker image inspect "ghcr.io/volcengine/openviking:<tested-version>" \
  --format '{{index .RepoDigests 0}}'
```

Configure embedding and VLM providers, models, endpoints, and API keys in a
copy of [`configs/ov.conf.example`](configs/ov.conf.example). Treat the file as
a secret: replace all placeholders, restrict its permissions, and do not commit
it or bake it into an image. The structured configuration and storage mount
interfaces are not implemented yet, so preparing this file does not enable
deployment.

## Launch

`scripts/launch_openviking.sh` validates a pinned base image and defines the
TC-API deployment flow, but currently exits before starting infrastructure or
submitting a deployment because the TC-API launch boundary cannot enforce the
required network and mount restrictions. Do not use a `latest` tag or add a
caller-controlled Docker command to work around this limitation.

Once the structured TC-API interfaces are available, the intended invocation
will be:

```bash
export OPENVIKING_VERSION="<tested-version>"
export OPENVIKING_BASE="ghcr.io/volcengine/openviking@sha256:<digest>"
./scripts/launch_openviking.sh
```

## Verify and connect OpenClaw

After a safely configured OpenViking workload is available, verify its health
before connecting OpenClaw:

```bash
curl -fsS http://127.0.0.1:1933/health
curl -fsS http://127.0.0.1:1933/ready
```

The OpenClaw gateway must meet the official plugin's Node.js and OpenClaw
version requirements. Create a dedicated User API Key; never give OpenClaw the
Root Key.

```bash
export OPENVIKING_API_KEY="<openviking-user-key>"
../OpenClaw/scripts/connect_openclaw_openviking.sh
```

The connection script checks both service probes, installs the official
OpenViking plugin, configures `http://127.0.0.1:1933`, and displays plugin
status. Ensure the gateway state is persistent so the plugin and its
configuration survive recreation.

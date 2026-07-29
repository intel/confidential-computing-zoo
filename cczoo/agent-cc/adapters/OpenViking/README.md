# OpenViking Adapter

This adapter deploys the official OpenViking server as the `openviking-cmem`
workload and connects it to OpenClaw through the official plugin.

## Security model

The launched container has the label `argus.workload=openviking-cmem`, publishes
only `127.0.0.1:1933`, and uses `/app/.openviking` for all OpenViking state.
It does not run privileged and does not use host networking.

## Prerequisites

Before launching, select an embedding provider/model and VLM provider/model.
From `cczoo/agent-cc/adapters/OpenViking`, create a restricted configuration
file in the selected storage mount:

```bash
export OPENVIKING_LUKS_MOUNT_ROOT="<mounted-storage-path>"
export OPENVIKING_LUKS_SUBDIR=openviking
OPENVIKING_HOST_DATA_DIR="${OPENVIKING_LUKS_MOUNT_ROOT}/${OPENVIKING_LUKS_SUBDIR}"
mkdir -p "$OPENVIKING_HOST_DATA_DIR"
cp configs/ov.conf.example "$OPENVIKING_HOST_DATA_DIR/ov.conf"
chmod 700 "$OPENVIKING_HOST_DATA_DIR"
chmod 600 "$OPENVIKING_HOST_DATA_DIR/ov.conf"
```

Pull and record an official, tested image digest. Do not use `latest` for a
launchable image.

```bash
docker pull "ghcr.io/volcengine/openviking:<tested-version>"
docker image inspect "ghcr.io/volcengine/openviking:<tested-version>" \
  --format '{{index .RepoDigests 0}}'
```

Validate the configuration against that digest before deployment:

```bash
docker run --rm \
  -v "$OPENVIKING_HOST_DATA_DIR:/app/.openviking" \
  "ghcr.io/volcengine/openviking@sha256:<digest>" \
  openviking-server doctor
```

## Launch

`launch_openviking.sh` creates a thin local image from
`configs/Dockerfile.openviking`, pushes it to the local registry, and
submits the deployment to TC API. It requires a release identifier and a pinned
base image digest.

```bash
export OPENVIKING_VERSION="<tested-version>"
export OPENVIKING_BASE="ghcr.io/volcengine/openviking@sha256:<digest>"
(cd scripts && ./launch_openviking.sh)
```

The default launch command is equivalent to:

```text
docker run -d --name=agentcc-openviking-service \
  --label=argus.workload=openviking-cmem \
  --publish=127.0.0.1:1933:1933 \
  --env=OPENVIKING_CONFIG_FILE=/app/.openviking/ov.conf \
  --env=OPENVIKING_WITH_BOT=0 \
  --volume="${OPENVIKING_HOST_DATA_DIR}:/app/.openviking"
```

## Verify

```bash
curl -fsS http://127.0.0.1:1933/health
curl -fsS http://127.0.0.1:1933/ready
```

## Connect OpenClaw

The OpenClaw gateway must meet the official plugin's Node.js and OpenClaw version
requirements. Provide the user key only through the environment and configure the
official plugin:

```bash
export OPENVIKING_API_KEY="<openclaw-user-key>"
../OpenClaw/scripts/connect_openclaw_openviking.sh
```

The script checks both service probes, installs the official plugin, configures
`http://127.0.0.1:1933`, and displays plugin status. Ensure the gateway state is
persistent so the installed plugin and its configuration survive recreation.

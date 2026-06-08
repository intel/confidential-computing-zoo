#!/usr/bin/env bash

# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# run-sbx.sh — Build and run openclaw-sbx via plain docker run (no Compose)
#
# Usage:
#   ./scripts/docker/run-sbx.sh [--build] [--token TOKEN] [--port PORT]
#                                [--bind BIND] [--name NAME] [--no-start]
#
# Options:
#   --build          Force rebuild of the openclaw-sbx:latest image before run.
#   --token TOKEN    Gateway auth token. Generated and printed if omitted.
#   --port PORT      Host port for gateway (default: 18789).
#   --bind BIND      Gateway bind mode: lan | loopback (default: lan).
#   --name NAME      Container name (default: openclaw-gateway).
#   --no-start       Only build the image; do not start the container.
#
# Prerequisites:
#   - Docker daemon running and accessible
#   - docker.sock at /var/run/docker.sock (or set OPENCLAW_DOCKER_SOCKET)
#   - openclaw-sandbox:bookworm-slim image built (script offers to build it)
#
# Named volumes used (no host paths exposed):
#   openclaw-config     →  /home/node/.openclaw           (gateway config)
#   openclaw-workspace  →  /home/node/.openclaw/workspace (user workspace)
#
# Mandatory Docker access mount (see Dockerfile.sbx header for explanation):
#   Default host docker.sock path: bind the socket file to /var/run/docker.sock
#   Alternate proxy socket path: bind the parent directory and export DOCKER_HOST
#
# To remove all persisted data:
#   docker volume rm openclaw-config openclaw-workspace

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="openclaw-sbx:latest"
CONTAINER_NAME="openclaw-gateway"
GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-18790}"
GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
GATEWAY_TOKEN="${OPENCLAW_GATEWAY_TOKEN:-}"
DOCKER_SOCKET="${OPENCLAW_DOCKER_SOCKET:-}"
CONTAINER_DOCKER_HOST=""
DOCKER_MOUNT_ARGS=()
DOCKER_HOST_ENV_ARGS=()
DO_BUILD=0
NO_START=0
CONFIG_VOLUME="${OPENCLAW_CONFIG_VOLUME:-openclaw-config}"
WORKSPACE_VOLUME="${OPENCLAW_WORKSPACE_VOLUME:-openclaw-workspace}"

fail() { echo "ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Prestart helpers — plain docker run with volumes mounted, no gateway process
#
# These functions run one-off containers to read/write the named config volume
# before the long-running gateway container starts.  Equivalent to setup.sh's
# run_prestart_cli() / run_prestart_gateway(), but without Compose.
# ---------------------------------------------------------------------------

# Run a sh -c command in the image as root, with both volumes mounted.
prestart_sh_root() {
  docker run --rm \
    --user root \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    -v "${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace" \
    --entrypoint sh \
    "$IMAGE" -c "$1"
}

# Run a sh -c command in the image as node, with both volumes mounted.
prestart_sh_node() {
  docker run --rm \
    --user node \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    -v "${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace" \
    --entrypoint sh \
    "$IMAGE" -c "$1"
}

# Run node /app/dist/index.js <subcommand> as node, non-interactively.
prestart_cli() {
  docker run --rm \
    --user node \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    -v "${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace" \
    ${GATEWAY_TOKEN:+-e "OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}"} \
    --entrypoint node \
    "$IMAGE" /app/dist/index.js "$@"
}

# Same as prestart_cli but with stdin + tty — for interactive prompts.
prestart_cli_interactive() {
  local tty_flag=""
  [[ -t 0 ]] && tty_flag="--tty"
  docker run --rm -i $tty_flag \
    --user node \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    -v "${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace" \
    ${GATEWAY_TOKEN:+-e "OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}"} \
    --entrypoint node \
    "$IMAGE" /app/dist/index.js "$@"
}

# ---------------------------------------------------------------------------
# Parse arguments
# ---------------------------------------------------------------------------

while [[ $# -gt 0 ]]; do
  case "$1" in
    --build)    DO_BUILD=1 ;;
    --no-start) NO_START=1 ;;
    --token)    GATEWAY_TOKEN="${2:-}"; shift ;;
    --port)     GATEWAY_PORT="${2:-}"; shift ;;
    --bind)     GATEWAY_BIND="${2:-}"; shift ;;
    --name)     CONTAINER_NAME="${2:-}"; shift ;;
    *) fail "Unknown option: $1" ;;
  esac
  shift
done

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------

command -v docker >/dev/null 2>&1 || fail "docker not found."

# Resolve docker socket
[[ -z "$DOCKER_SOCKET" && "${DOCKER_HOST:-}" == unix://* ]] && \
  DOCKER_SOCKET="${DOCKER_HOST#unix://}"
[[ -z "$DOCKER_SOCKET" ]] && DOCKER_SOCKET="/var/run/docker.sock"
[[ -S "$DOCKER_SOCKET" ]] || \
  fail "Docker socket not found at $DOCKER_SOCKET. Sandbox mode requires docker.sock."

if [[ "$DOCKER_SOCKET" == "/var/run/docker.sock" ]]; then
  DOCKER_MOUNT_ARGS=(-v "${DOCKER_SOCKET}:/var/run/docker.sock")
else
  DOCKER_SOCKET_DIR="$(dirname "$DOCKER_SOCKET")"
  DOCKER_SOCKET_BASENAME="$(basename "$DOCKER_SOCKET")"
  DOCKER_MOUNT_ARGS=(-v "${DOCKER_SOCKET_DIR}:${DOCKER_SOCKET_DIR}")
  CONTAINER_DOCKER_HOST="unix://${DOCKER_SOCKET_DIR}/${DOCKER_SOCKET_BASENAME}"
  DOCKER_HOST_ENV_ARGS=(-e "DOCKER_HOST=${CONTAINER_DOCKER_HOST}")
fi

# Detect GID of docker.sock — the gateway container's 'node' user must be in
# this group to read/write the socket without running as root.
DOCKER_GID="$(stat -c '%g' "$DOCKER_SOCKET" 2>/dev/null || \
              stat -f '%g' "$DOCKER_SOCKET" 2>/dev/null || echo "")"
[[ -n "$DOCKER_GID" ]] || fail "Cannot determine GID of $DOCKER_SOCKET."

# ---------------------------------------------------------------------------
# Build openclaw-sbx image
# ---------------------------------------------------------------------------

build_image() {
  echo ""
  echo "==> Building image: $IMAGE"
  docker build \
    -f "$ROOT_DIR/Dockerfile.sbx" \
    -t "$IMAGE" \
    "$ROOT_DIR"
  echo "==> Image built: $IMAGE"
}

# Build if forced, or if the image does not yet exist
if [[ "$DO_BUILD" -eq 1 ]]; then
  build_image
elif ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Image $IMAGE not found locally — building..."
  build_image
fi

# Verify Docker CLI is present inside the image (required for sibling containers)
echo ""
echo "==> Verifying Docker CLI inside $IMAGE"
docker run --rm --entrypoint docker "$IMAGE" --version >/dev/null 2>&1 || \
  fail "Docker CLI not found in $IMAGE. Rebuild the image."

[[ "$NO_START" -eq 1 ]] && { echo "==> --no-start: image ready, not starting container."; exit 0; }

# ---------------------------------------------------------------------------
# Interactive prestart configuration
#
# Runs only on first boot (marker file absent in the config named volume).
# All writes go directly into the named volume via one-off containers, so
# when the gateway starts it finds config already in place and the entrypoint
# skips its own init block.
# ---------------------------------------------------------------------------

INIT_MARKER="/home/node/.openclaw/.sbx-initialized"

FIRST_BOOT=0
if ! docker run --rm \
    --user node \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    --entrypoint sh "$IMAGE" \
    -c "test -f ${INIT_MARKER}" 2>/dev/null; then
  FIRST_BOOT=1
fi

if [[ "$FIRST_BOOT" -eq 1 ]]; then
  echo ""
  echo "========================================"
  echo " OpenClaw Gateway — First-time Setup"
  echo "========================================"
  echo " Config volume : $CONFIG_VOLUME"
  echo " Workspace vol : $WORKSPACE_VOLUME"
  echo " Gateway bind  : $GATEWAY_BIND"
  echo " Gateway port  : $GATEWAY_PORT"
  echo ""

  # ---- Token prompt -------------------------------------------------------
  if [[ -z "$GATEWAY_TOKEN" ]]; then
    echo "Gateway auth token"
    echo "  Enter a token string, or press Enter to auto-generate one:"
    read -r _input_token
    if [[ -n "$_input_token" ]]; then
      GATEWAY_TOKEN="$_input_token"
      echo "Using provided token."
    else
      if command -v openssl >/dev/null 2>&1; then
        GATEWAY_TOKEN="$(openssl rand -hex 32)"
      else
        GATEWAY_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
      fi
      echo ""
      echo "  Auto-generated token (save this — shown once only):"
      echo "  $GATEWAY_TOKEN"
    fi
    echo ""
  fi

  # ---- Fix volume ownership -----------------------------------------------
  echo "==> Fixing volume ownership"
  prestart_sh_root \
    'find /home/node/.openclaw -xdev -exec chown node:node {} + 2>/dev/null; \
     [ -d /home/node/.openclaw/workspace/.openclaw ] && \
       chown -R node:node /home/node/.openclaw/workspace/.openclaw 2>/dev/null || true'

  # ---- Seed directory structure -------------------------------------------
  prestart_sh_node 'mkdir -p \
    /home/node/.openclaw/identity \
    /home/node/.openclaw/agents/main/agent \
    /home/node/.openclaw/agents/main/sessions'

  # ---- Interactive onboard ------------------------------------------------
  echo ""
  echo "==> Onboarding (interactive)"
  echo "    Gateway mode is pinned to 'local' for Docker deployments."
  echo "    Tailscale: configure at the host level separately."
  echo "    Daemon install: skipped — lifecycle managed by Docker."
  echo ""
  prestart_cli_interactive onboard --mode local --no-install-daemon

  # ---- Gateway defaults ---------------------------------------------------
  echo ""
  echo "==> Writing gateway defaults"
  prestart_cli config set gateway.mode  local          >/dev/null
  prestart_cli config set gateway.bind  "$GATEWAY_BIND" >/dev/null
  echo "    Pinned gateway.mode=local, gateway.bind=$GATEWAY_BIND"

  # ---- Sandbox config -----------------------------------------------------
  echo ""
  echo "==> Writing sandbox config"
  sandbox_ok=true
  prestart_cli config set agents.defaults.sandbox.mode \
    "${OPENCLAW_SANDBOX_MODE:-all}"                                          >/dev/null || sandbox_ok=false
  prestart_cli config set agents.defaults.sandbox.scope         "session"      >/dev/null || sandbox_ok=false
  prestart_cli config set agents.defaults.sandbox.workspaceAccess \
    "${OPENCLAW_WORKSPACE_ACCESS:-rw}"                                        >/dev/null || sandbox_ok=false
  prestart_cli config set agents.defaults.sandbox.backend       "docker"     >/dev/null || sandbox_ok=false

  if [[ "$sandbox_ok" != true ]]; then
    fail "Sandbox config write failed. Aborting — gateway NOT started."
  fi
  echo "    mode=${OPENCLAW_SANDBOX_MODE:-all}, scope=agent, workspaceAccess=${OPENCLAW_WORKSPACE_ACCESS:-rw}, backend=docker"

  # ---- Control UI allowlist (non-loopback only) ---------------------------
  if [[ "$GATEWAY_BIND" != "loopback" ]]; then
    _origins="[\"http://localhost:${GATEWAY_PORT}\",\"http://127.0.0.1:${GATEWAY_PORT}\"]"
    prestart_cli config set gateway.controlUi.allowedOrigins "$_origins" \
      --strict-json >/dev/null || true
    echo "    Set controlUi.allowedOrigins for non-loopback bind."
  fi

  # ---- Write initialization marker ----------------------------------------
  # The marker is written ONLY after all config steps succeed.
  # entrypoint-sbx.sh checks for this file and skips re-initialization.
  docker run --rm --user node \
    -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
    --entrypoint sh "$IMAGE" \
    -c "touch ${INIT_MARKER}"
  echo ""
  echo "==> Configuration complete."

  # ---- Optional channel setup prompt -------------------------------------
  echo ""
  echo "==> Channel setup (optional — can be done after gateway starts)"
  echo "    WhatsApp (QR scan):"
  echo "      docker exec -it $CONTAINER_NAME node /app/dist/index.js channels login"
  echo "    Telegram (bot token):"
  echo "      docker exec -it $CONTAINER_NAME node /app/dist/index.js channels add --channel telegram --token <token>"
  echo "    Discord (bot token):"
  echo "      docker exec -it $CONTAINER_NAME node /app/dist/index.js channels add --channel discord --token <token>"
  echo "    Docs: https://docs.openclaw.ai/channels"
  echo ""
  echo "Press Enter to start the gateway, or Ctrl+C to abort."
  read -r _

else
  echo ""
  echo "==> Config volume already initialized — skipping interactive setup."
  echo "    To force re-setup: docker run --rm --user node \\"
  echo "      -v ${CONFIG_VOLUME}:/home/node/.openclaw --entrypoint sh $IMAGE \\"
  echo "      -c 'rm /home/node/.openclaw/.sbx-initialized'"
fi

# ---------------------------------------------------------------------------
# Build sandbox image (sibling containers launched by gateway for tool exec)
# ---------------------------------------------------------------------------

if ! docker image inspect "openclaw-sandbox:bookworm-slim" >/dev/null 2>&1; then
  echo ""
  echo "==> sandbox image 'openclaw-sandbox:bookworm-slim' not found."
  if [[ -f "$ROOT_DIR/Dockerfile.sandbox" ]]; then
    echo "==> Building sandbox image..."
    docker build \
      -t "openclaw-sandbox:bookworm-slim" \
      -f "$ROOT_DIR/Dockerfile.sandbox" \
      "$ROOT_DIR"
  else
    echo "WARNING: Dockerfile.sandbox not found." >&2
    echo "  Skill/tool sandbox execution will fail until the sandbox image exists." >&2
  fi
else
  echo "==> Sandbox image found: openclaw-sandbox:bookworm-slim"
fi

# ---------------------------------------------------------------------------
# Remove existing container if present (rerun idempotency)
# ---------------------------------------------------------------------------

if docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo ""
  echo "==> Container '$CONTAINER_NAME' already exists — removing before restart."
  docker rm -f "$CONTAINER_NAME"
fi

# ---------------------------------------------------------------------------
# Start gateway container
# ---------------------------------------------------------------------------

echo ""
echo "==> Starting container: $CONTAINER_NAME"
echo "    Image          : $IMAGE"
echo "    Config volume  : $CONFIG_VOLUME  →  /home/node/.openclaw"
echo "    Workspace vol  : $WORKSPACE_VOLUME  →  /home/node/.openclaw/workspace"
if [[ -n "$CONTAINER_DOCKER_HOST" ]]; then
  echo "    docker mount   : $(dirname "$DOCKER_SOCKET")  →  $(dirname "${CONTAINER_DOCKER_HOST#unix://}")  [directory bind via DOCKER_HOST]"
  echo "    DOCKER_HOST    : $CONTAINER_DOCKER_HOST"
else
  echo "    docker.sock    : $DOCKER_SOCKET  [bind mount — mandatory for sandbox]"
fi
echo "    Docker GID     : $DOCKER_GID"
echo "    Gateway port   : $GATEWAY_PORT"
echo "    Gateway bind   : $GATEWAY_BIND"
if [[ -n "$GATEWAY_TOKEN" ]]; then
  echo "    Token          : (provided via --token / env)"
else
  echo "    Token          : (will be auto-generated on first boot — check logs)"
fi
# Build -e token argument safely as an array so quoting is handled correctly.
# Using ${var:+word} inline in the docker run command would produce a single
# string with literal quotes rather than two separate arguments.
TOKEN_ENV_ARGS=()
[[ -n "$GATEWAY_TOKEN" ]] && TOKEN_ENV_ARGS=(-e "OPENCLAW_GATEWAY_TOKEN=${GATEWAY_TOKEN}")

echo ''

docker run \
  --detach \
  --name "$CONTAINER_NAME" \
  --init \
  --restart unless-stopped \
  -v "${CONFIG_VOLUME}:/home/node/.openclaw" \
  -v "${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace" \
  "${DOCKER_MOUNT_ARGS[@]}" \
  --group-add "$DOCKER_GID" \
  -v /etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf \
  -v /dev/tdx_guest:/dev/tdx_guest \
  -v /usr/share/doc/libtdx-attest-dev/examples/:/td-attest/ \
  -v /etc/tdx-attest.conf:/etc/tdx-attest.conf \
  -p "${GATEWAY_PORT}:18789" \
  -p "${BRIDGE_PORT}:18790" \
  -e "OPENCLAW_GATEWAY_PORT=${GATEWAY_PORT}" \
  -e "OPENCLAW_GATEWAY_BIND=${GATEWAY_BIND}" \
  "${DOCKER_HOST_ENV_ARGS[@]}" \
  "${TOKEN_ENV_ARGS[@]}" \
  "$IMAGE"
# ---------------------------------------------------------------------------
# Post-start summary
# ---------------------------------------------------------------------------

echo ""
echo "==> Container started: $CONTAINER_NAME"
echo ""
echo "Commands:"
echo "  docker logs -f $CONTAINER_NAME"
echo "  docker exec $CONTAINER_NAME node /app/dist/index.js health --token <token>"
echo "  docker exec -it $CONTAINER_NAME node /app/dist/index.js channels login"
echo ""
if [[ -z "$GATEWAY_TOKEN" ]]; then
  echo "  To retrieve the auto-generated token:"
  echo "  docker logs $CONTAINER_NAME 2>&1 | grep -A1 'Gateway token'"
  echo ""
fi
echo "  To stop:  docker stop $CONTAINER_NAME"
echo "  To remove: docker rm -f $CONTAINER_NAME"
echo "  To wipe data: docker volume rm $CONFIG_VOLUME $WORKSPACE_VOLUME"

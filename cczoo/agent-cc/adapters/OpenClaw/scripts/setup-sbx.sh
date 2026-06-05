#!/usr/bin/env bash
# setup-sbx.sh — Sandbox-mode Docker setup for OpenClaw Gateway
#
# NOTE (when run from openclaw-sbx-test/):
#   This script builds from the full openclaw repo Dockerfile and
#   docker-compose.yml.  It must be run from the repo root, or the repo root
#   must be two levels above this file's location.
#   For a fully self-contained run (no repo needed), use run-sbx.sh instead —
#   that script extends ghcr.io/openclaw/openclaw:latest and requires only
#   the files in openclaw-sbx-test/.
#
# Differences from setup.sh:
#
#   1. No host filesystem bind mounts for OpenClaw data.
#      Config (/home/node/.openclaw) and workspace (/home/node/.openclaw/workspace)
#      use Docker named volumes — data persists inside Docker-managed storage
#      and is never exposed as a host directory path.
#
#      ONE bind mount is retained and cannot be removed:
#      ┌────────────────────────────────────────────────────────────────────────┐
#      │  /var/run/docker.sock  →  /var/run/docker.sock  (bind mount, mandatory)│
#      │                                                                        │
#      │  Reason: docker.sock is a Unix domain socket owned by the host kernel. │
#      │  It cannot be stored in or replicated by a Docker named volume.        │
#      │  The gateway must talk to the host Docker daemon to create sandbox /   │
#      │  skill sibling containers (DooD pattern). There is no alternative.     │
#      └────────────────────────────────────────────────────────────────────────┘
#
#   2. Sandbox mode is always enabled.
#      OPENCLAW_INSTALL_DOCKER_CLI is forced to 1 so the gateway image contains
#      Docker CLI — required for the gateway to launch sibling containers via
#      the mounted docker.sock.
#
#   3. A self-contained docker-compose.sbx.yml is generated and used in place
#      of docker-compose.yml.  The gateway token is persisted to .env (since
#      we have no host-side config directory to read from).

set -euo pipefail
set -x

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SBX_COMPOSE_FILE="$ROOT_DIR/docker-compose.sbx.yml"
ENV_FILE="$ROOT_DIR/.env"

IMAGE_NAME="${OPENCLAW_IMAGE:-openclaw:local}"
DOCKER_SOCKET_PATH="${OPENCLAW_DOCKER_SOCKET:-}"
TIMEZONE="${OPENCLAW_TZ:-}"

# Named volumes — written as literals into the compose file because Docker
# Compose does not support variable substitution in top-level volume keys.
CONFIG_VOLUME="${OPENCLAW_CONFIG_VOLUME:-openclaw-config}"
WORKSPACE_VOLUME="${OPENCLAW_WORKSPACE_VOLUME:-openclaw-workspace}"

# Sandbox is always on in this script.
export OPENCLAW_INSTALL_DOCKER_CLI=1

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

fail() { echo "ERROR: $*" >&2; exit 1; }

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing dependency: $1" >&2; exit 1; }
}

read_env_gateway_token() {
  local env_path="$1" line token=""
  [[ -f "$env_path" ]] || return 0
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ "$line" == OPENCLAW_GATEWAY_TOKEN=* ]] && token="${line#OPENCLAW_GATEWAY_TOKEN=}"
  done <"$env_path"
  [[ -n "$token" ]] && printf '%s' "$token"
}

contains_disallowed_chars() {
  [[ "$1" == *$'\n'* || "$1" == *$'\r'* || "$1" == *$'\t'* ]]
}

is_valid_timezone() {
  [[ -e "/usr/share/zoneinfo/$1" && ! -d "/usr/share/zoneinfo/$1" ]]
}

validate_volume_name() {
  [[ "$1" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]*$ ]] || \
    fail "Volume name '$1' must match [A-Za-z0-9][A-Za-z0-9_.-]*"
}

upsert_env() {
  local file="$1"; shift
  local -a keys=("$@")
  local tmp seen=" "
  tmp="$(mktemp)"
  if [[ -f "$file" ]]; then
    while IFS= read -r line || [[ -n "$line" ]]; do
      local key="${line%%=*}" replaced=false
      for k in "${keys[@]}"; do
        if [[ "$key" == "$k" ]]; then
          printf '%s=%s\n' "$k" "${!k-}" >>"$tmp"
          seen="$seen$k "; replaced=true; break
        fi
      done
      [[ "$replaced" == false ]] && printf '%s\n' "$line" >>"$tmp"
    done <"$file"
  fi
  for k in "${keys[@]}"; do
    [[ "$seen" != *" $k "* ]] && printf '%s=%s\n' "$k" "${!k-}" >>"$tmp"
  done
  mv "$tmp" "$file"
}

# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

require_cmd docker
docker compose version >/dev/null 2>&1 || { echo "Docker Compose not available." >&2; exit 1; }

# Resolve Docker socket path
[[ -z "$DOCKER_SOCKET_PATH" && "${DOCKER_HOST:-}" == unix://* ]] && \
  DOCKER_SOCKET_PATH="${DOCKER_HOST#unix://}"
[[ -z "$DOCKER_SOCKET_PATH" ]] && DOCKER_SOCKET_PATH="/var/run/docker.sock"
[[ -S "$DOCKER_SOCKET_PATH" ]] || \
  fail "Docker socket not found at $DOCKER_SOCKET_PATH (required for sandbox mode)."

# Timezone validation
if [[ -n "$TIMEZONE" ]]; then
  contains_disallowed_chars "$TIMEZONE" && fail "OPENCLAW_TZ contains control characters."
  [[ "$TIMEZONE" =~ ^[A-Za-z0-9/_+\-]+$ ]] || fail "OPENCLAW_TZ must be a valid IANA timezone string."
  is_valid_timezone "$TIMEZONE" || fail "OPENCLAW_TZ not found in /usr/share/zoneinfo."
fi

validate_volume_name "$CONFIG_VOLUME"
validate_volume_name "$WORKSPACE_VOLUME"

# Detect host docker group GID — added via group_add so the 'node' user inside
# the container can read/write docker.sock without running as root.
DOCKER_GID="$(stat -c '%g' "$DOCKER_SOCKET_PATH" 2>/dev/null || \
              stat -f '%g' "$DOCKER_SOCKET_PATH" 2>/dev/null || echo "")"
[[ -n "$DOCKER_GID" ]] || fail "Cannot determine GID of $DOCKER_SOCKET_PATH."

# ---------------------------------------------------------------------------
# Resolve and export runtime variables
# ---------------------------------------------------------------------------

export OPENCLAW_GATEWAY_PORT="${OPENCLAW_GATEWAY_PORT:-18789}"
export OPENCLAW_BRIDGE_PORT="${OPENCLAW_BRIDGE_PORT:-18790}"
export OPENCLAW_GATEWAY_BIND="${OPENCLAW_GATEWAY_BIND:-lan}"
export OPENCLAW_IMAGE="$IMAGE_NAME"
export OPENCLAW_DOCKER_SOCKET="$DOCKER_SOCKET_PATH"
export DOCKER_GID
export OPENCLAW_TZ="$TIMEZONE"
export OPENCLAW_CONFIG_VOLUME="$CONFIG_VOLUME"
export OPENCLAW_WORKSPACE_VOLUME="$WORKSPACE_VOLUME"

# Token persistence: because data lives in Docker named volumes (not on the
# host filesystem), we cannot read the token back from openclaw.json on the
# host.  The .env file is the sole persistence mechanism for the token.
if [[ -z "${OPENCLAW_GATEWAY_TOKEN:-}" ]]; then
  EXISTING_TOKEN="$(read_env_gateway_token "$ENV_FILE" || true)"
  if [[ -n "$EXISTING_TOKEN" ]]; then
    OPENCLAW_GATEWAY_TOKEN="$EXISTING_TOKEN"
    echo "Reusing gateway token from $ENV_FILE"
  elif command -v openssl >/dev/null 2>&1; then
    OPENCLAW_GATEWAY_TOKEN="$(openssl rand -hex 32)"
  else
    OPENCLAW_GATEWAY_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  fi
fi
export OPENCLAW_GATEWAY_TOKEN

upsert_env "$ENV_FILE" \
  OPENCLAW_GATEWAY_PORT \
  OPENCLAW_BRIDGE_PORT \
  OPENCLAW_GATEWAY_BIND \
  OPENCLAW_GATEWAY_TOKEN \
  OPENCLAW_IMAGE \
  OPENCLAW_DOCKER_SOCKET \
  DOCKER_GID \
  OPENCLAW_INSTALL_DOCKER_CLI \
  OPENCLAW_TZ \
  OPENCLAW_CONFIG_VOLUME \
  OPENCLAW_WORKSPACE_VOLUME

# ---------------------------------------------------------------------------
# Generate docker-compose.sbx.yml
#
# Volume names (CONFIG_VOLUME, WORKSPACE_VOLUME, DOCKER_SOCKET_PATH) are
# bash-expanded here so their literal values appear in the file.  All other
# runtime values (\${...}) are left as Docker Compose env-var references
# resolved at `docker compose up` time from .env.
# ---------------------------------------------------------------------------

generate_compose() {
  cat >"$SBX_COMPOSE_FILE" <<YAML
# docker-compose.sbx.yml — generated by setup-sbx.sh
# Uses Docker named volumes for OpenClaw data (no host bind mounts).
# docker.sock is retained as a bind mount — see header comment in setup-sbx.sh.
services:
  openclaw-gateway:
    image: \${OPENCLAW_IMAGE:-openclaw:local}
    environment:
      HOME: /home/node
      TERM: xterm-256color
      OPENCLAW_GATEWAY_TOKEN: \${OPENCLAW_GATEWAY_TOKEN:-}
      OPENCLAW_ALLOW_INSECURE_PRIVATE_WS: \${OPENCLAW_ALLOW_INSECURE_PRIVATE_WS:-}
      TZ: \${OPENCLAW_TZ:-UTC}
    volumes:
      # Named volumes: OpenClaw config and workspace persist in Docker-managed
      # storage without any host filesystem path exposure.
      - ${CONFIG_VOLUME}:/home/node/.openclaw
      - ${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace
      # Mandatory bind mount: docker.sock is a Unix domain socket supplied by
      # the host kernel and cannot be stored in a named volume.  Gateway needs
      # it to launch sandbox / skill sibling containers (DooD pattern).
      - ${DOCKER_SOCKET_PATH}:/var/run/docker.sock
    group_add:
      # Grant the 'node' container user access to docker.sock by adding it to
      # the host docker group.  GID is detected at setup time from the socket.
      - "\${DOCKER_GID}"
    ports:
      - "\${OPENCLAW_GATEWAY_PORT:-18789}:18789"
      - "\${OPENCLAW_BRIDGE_PORT:-18790}:18790"
    init: true
    restart: unless-stopped
    command:
      - node
      - dist/index.js
      - gateway
      - --bind
      - \${OPENCLAW_GATEWAY_BIND:-lan}
      - --port
      - "18789"
    healthcheck:
      test:
        - CMD
        - node
        - -e
        - "fetch('http://127.0.0.1:18789/healthz').then((r)=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"
      interval: 30s
      timeout: 5s
      retries: 5
      start_period: 20s

  openclaw-cli:
    image: \${OPENCLAW_IMAGE:-openclaw:local}
    network_mode: "service:openclaw-gateway"
    cap_drop:
      - NET_RAW
      - NET_ADMIN
    security_opt:
      - no-new-privileges:true
    environment:
      HOME: /home/node
      TERM: xterm-256color
      OPENCLAW_GATEWAY_TOKEN: \${OPENCLAW_GATEWAY_TOKEN:-}
      BROWSER: echo
      TZ: \${OPENCLAW_TZ:-UTC}
    volumes:
      - ${CONFIG_VOLUME}:/home/node/.openclaw
      - ${WORKSPACE_VOLUME}:/home/node/.openclaw/workspace
    stdin_open: true
    tty: true
    init: true
    entrypoint: ["node", "dist/index.js"]
    depends_on:
      - openclaw-gateway

volumes:
  # Named volume declarations — Docker manages storage lifecycle.
  # Remove these volumes with: docker volume rm ${CONFIG_VOLUME} ${WORKSPACE_VOLUME}
  ${CONFIG_VOLUME}:
  ${WORKSPACE_VOLUME}:
YAML
}

generate_compose

COMPOSE_ARGS=("-f" "$SBX_COMPOSE_FILE")
COMPOSE_HINT="docker compose -f ${SBX_COMPOSE_FILE}"

# ---------------------------------------------------------------------------
# Compose helpers
# ---------------------------------------------------------------------------

run_prestart_gateway() {
  docker compose "${COMPOSE_ARGS[@]}" run --rm --no-deps "$@"
}

# Run CLI commands on the gateway container image directly, bypassing
# openclaw-cli's network_mode dependency on a running gateway — same
# pattern as setup.sh:run_prestart_cli().
run_prestart_cli() {
  run_prestart_gateway --entrypoint node openclaw-gateway dist/index.js "$@"
}

ensure_control_ui_allowed_origins() {
  [[ "${OPENCLAW_GATEWAY_BIND}" == "loopback" ]] && return 0
  local allowed_origin_json current
  allowed_origin_json="$(printf '["http://localhost:%s","http://127.0.0.1:%s"]' \
    "$OPENCLAW_GATEWAY_PORT" "$OPENCLAW_GATEWAY_PORT")"
  current="$(run_prestart_cli config get gateway.controlUi.allowedOrigins 2>/dev/null || true)"
  current="${current//$'\r'/}"
  if [[ -n "$current" && "$current" != "null" && "$current" != "[]" ]]; then
    echo "Control UI allowlist already configured; leaving unchanged."
    return 0
  fi
  run_prestart_cli config set gateway.controlUi.allowedOrigins \
    "$allowed_origin_json" --strict-json >/dev/null
  echo "Set gateway.controlUi.allowedOrigins to $allowed_origin_json."
}

sync_gateway_mode_and_bind() {
  run_prestart_cli config set gateway.mode local >/dev/null
  run_prestart_cli config set gateway.bind "$OPENCLAW_GATEWAY_BIND" >/dev/null
  echo "Pinned gateway.mode=local and gateway.bind=$OPENCLAW_GATEWAY_BIND."
}

# ---------------------------------------------------------------------------
# Build / pull image  (Docker CLI must be baked in for sandbox)
# ---------------------------------------------------------------------------

echo ""
if [[ "$IMAGE_NAME" == "openclaw:local" ]]; then
  echo "==> Building Docker image: $IMAGE_NAME (OPENCLAW_INSTALL_DOCKER_CLI=1)"
  DOCKER_BUILDKIT=1 docker build \
    --build-arg "OPENCLAW_INSTALL_DOCKER_CLI=1" \
    -t "$IMAGE_NAME" \
    -f "$ROOT_DIR/Dockerfile" \
    "$ROOT_DIR"
else
  echo "==> Pulling Docker image: $IMAGE_NAME"
  docker pull "$IMAGE_NAME" || fail "Failed to pull $IMAGE_NAME."
fi

# Verify Docker CLI presence — the gateway cannot create sibling containers
# without it, regardless of whether docker.sock is mounted.
echo "==> Verifying Docker CLI inside image"
docker run --rm --entrypoint docker "$IMAGE_NAME" --version >/dev/null 2>&1 || \
  fail "Docker CLI not found in $IMAGE_NAME. Rebuild with --build-arg OPENCLAW_INSTALL_DOCKER_CLI=1."

# ---------------------------------------------------------------------------
# Fix named-volume ownership
#
# Docker creates named volumes owned by root on first use.  The gateway
# process runs as 'node' (uid 1000) and needs write access.  Running a brief
# root container to chown is the portable idiom — works regardless of host uid.
# -xdev restricts traversal to the config volume boundary, preventing chown
# from crossing the workspace mount point.  The workspace's .openclaw/
# metadata subdirectory is then chowned separately.
# ---------------------------------------------------------------------------

echo ""
echo "==> Fixing named-volume ownership"
run_prestart_gateway --user root --entrypoint sh openclaw-gateway -c \
  'find /home/node/.openclaw -xdev -exec chown node:node {} +; \
   [ -d /home/node/.openclaw/workspace/.openclaw ] && \
     chown -R node:node /home/node/.openclaw/workspace/.openclaw || true'

# ---------------------------------------------------------------------------
# Onboarding and gateway config
# (all written before gateway starts so it boots with correct config)
# ---------------------------------------------------------------------------

echo ""
echo "==> Onboarding"
run_prestart_cli onboard --mode local --no-install-daemon

echo ""
echo "==> Gateway defaults"
sync_gateway_mode_and_bind

echo ""
echo "==> Control UI origin allowlist"
ensure_control_ui_allowed_origins

# ---------------------------------------------------------------------------
# Apply sandbox config
#
# Written to the config named volume via a prestart container so the gateway
# reads the correct sandbox policy on first boot.
# If any write fails the script aborts before starting the gateway — this
# prevents docker.sock from being exposed with an incomplete sandbox policy.
# ---------------------------------------------------------------------------

echo ""
echo "==> Applying sandbox config"
sandbox_ok=true
run_prestart_cli config set agents.defaults.sandbox.mode "non-main"        >/dev/null || sandbox_ok=false
run_prestart_cli config set agents.defaults.sandbox.scope "session"          >/dev/null || sandbox_ok=false
run_prestart_cli config set agents.defaults.sandbox.workspaceAccess "none" >/dev/null || sandbox_ok=false

[[ "$sandbox_ok" == true ]] || \
  fail "Sandbox config write failed (see above). Gateway NOT started to avoid exposing docker.sock without a full sandbox policy."

echo "Sandbox config written: mode=non-main, scope=agent, workspaceAccess=none"

# ---------------------------------------------------------------------------
# Start gateway
# ---------------------------------------------------------------------------

echo ""
echo "==> Starting gateway"
docker compose "${COMPOSE_ARGS[@]}" up -d openclaw-gateway

# ---------------------------------------------------------------------------
# Build sandbox image
#
# The sandbox image is the container that gateway spawns as a sibling for
# each sandboxed tool/skill execution.  Build it locally so the gateway can
# pull it from the host's local image store through docker.sock.
# ---------------------------------------------------------------------------

echo ""
echo "==> Building sandbox image (openclaw-sandbox:bookworm-slim)"
if [[ -f "$ROOT_DIR/Dockerfile.sandbox" ]]; then
  docker build \
    -t "openclaw-sandbox:bookworm-slim" \
    -f "$ROOT_DIR/Dockerfile.sandbox" \
    "$ROOT_DIR"
else
  echo "WARNING: Dockerfile.sandbox not found — sandbox image not built." >&2
  echo "  Agent tool execution will fail until the sandbox image is available." >&2
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "============================================="
echo " OpenClaw Gateway — Sandbox Mode"
echo "============================================="
echo " Config volume  : $CONFIG_VOLUME"
echo " Workspace vol  : $WORKSPACE_VOLUME"
echo " docker.sock    : $DOCKER_SOCKET_PATH  [bind mount — mandatory, see header]"
echo " Token          : $OPENCLAW_GATEWAY_TOKEN"
echo " Port           : $OPENCLAW_GATEWAY_PORT"
echo "============================================="
echo ""
echo "Commands:"
echo "  ${COMPOSE_HINT} logs -f openclaw-gateway"
echo "  ${COMPOSE_HINT} exec openclaw-gateway node dist/index.js health --token \"$OPENCLAW_GATEWAY_TOKEN\""
echo "  ${COMPOSE_HINT} run --rm openclaw-cli channels login"
echo ""
echo "Remove volumes (destroys all config/workspace data):"
echo "  docker volume rm ${CONFIG_VOLUME} ${WORKSPACE_VOLUME}"

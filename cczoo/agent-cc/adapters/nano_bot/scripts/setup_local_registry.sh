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

# Ensures a plain-HTTP local Docker registry is running on the host and
# reachable from the CoCo dev container's docker network. This lets us
# distribute a locally-built nano_bot image to the TDX guest without pushing
# it to any public/external registry and without needing real TLS certs.
#
# Confidential Containers guest-pull fetches the container image from
# *inside* the TDX guest VM (via the Confidential Data Hub), independently of
# whatever the host's containerd already has cached. So the registry must be
# reachable from the guest's network, not just from the host.
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-tdx}"
LOCAL_REGISTRY_NAME="${LOCAL_REGISTRY_NAME:-nano-bot-local-registry}"
LOCAL_REGISTRY_PORT="${LOCAL_REGISTRY_PORT:-5000}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*" >&2; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }

# Print the gateway IP of the docker network that $CONTAINER_NAME is attached
# to. Containers on that same network reach host-published ports via this
# address, and (in this environment) it is also reachable from inside the
# QEMU/TDX guest because the guest's outbound NAT ultimately routes through
# the CoCo dev container's own network interface.
detect_registry_host() {
  "$CONTAINER_ENGINE" inspect "$CONTAINER_NAME" \
    --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' | head -1
}

ensure_registry_running() {
  if "$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$LOCAL_REGISTRY_NAME"; then
    log "Local registry '$LOCAL_REGISTRY_NAME' already running."
    return 0
  fi

  if "$CONTAINER_ENGINE" ps -a --format '{{.Names}}' | grep -Fxq "$LOCAL_REGISTRY_NAME"; then
    log "Starting existing local registry container '$LOCAL_REGISTRY_NAME'."
    "$CONTAINER_ENGINE" start "$LOCAL_REGISTRY_NAME" >/dev/null
    return 0
  fi

  log "Creating local registry container '$LOCAL_REGISTRY_NAME' on port $LOCAL_REGISTRY_PORT."
  mkdir -p /tmp/nano-bot-local-registry-data
  "$CONTAINER_ENGINE" run -d --name "$LOCAL_REGISTRY_NAME" --restart unless-stopped \
    -p "${LOCAL_REGISTRY_PORT}:5000" \
    -v /tmp/nano-bot-local-registry-data:/var/lib/registry \
    registry:2 >/dev/null
}

ensure_registry_running

REGISTRY_HOST="$(detect_registry_host)"
if [[ -z "$REGISTRY_HOST" ]]; then
  err "Could not detect docker network gateway for container '$CONTAINER_NAME'."
  exit 1
fi

REGISTRY_ADDRESS="${REGISTRY_HOST}:${LOCAL_REGISTRY_PORT}"
log "Local registry reachable at: $REGISTRY_ADDRESS (plain HTTP, no TLS)"

# Print just the address on stdout so other scripts can capture it with:
#   REGISTRY_ADDRESS="$(scripts/setup_local_registry.sh)"
echo "$REGISTRY_ADDRESS"

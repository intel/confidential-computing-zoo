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

# End-to-end local signed-image flow for nano_bot:
#   1. sign an image already present in the local registry,
#   2. start a Trustee KBS with the public key and image policy,
#   3. run the existing CoCo + TDX workload with guest-side verification.
#
# Private signing material is kept below SIGNED_IMAGES_STATE_DIR and is never
# copied to KBS. Set SIGNED_IMAGES_STATE_DIR to a persistent, private directory
# if the generated key must be reused across runs.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPRO_SCRIPT="$SCRIPT_DIR/repro_linux_coco_tdx.sh"

CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
COCO_CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-official}"
KBS_CONTAINER_NAME="${KBS_CONTAINER_NAME:-nano-bot-trustee-kbs}"
KBS_IMAGE="${KBS_IMAGE:-ghcr.io/confidential-containers/staged-images/kbs:c96dbe6bcc3d7529fdb27afb19a54a6625b29634}"
KBS_PORT="${KBS_PORT:-8080}"
KBS_GUEST_HOST="${KBS_GUEST_HOST:-}"
SIGNED_IMAGES_STATE_DIR="${SIGNED_IMAGES_STATE_DIR:-$HOME/.config/nano-bot-signed-images}"
REGISTRY_HOST="${REGISTRY_HOST:-127.0.0.1}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
LOCAL_REGISTRY_NAME="${LOCAL_REGISTRY_NAME:-}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-library/nano_bot}"
IMAGE_TAG="${IMAGE_TAG:-2.0}"
IMAGE_REFERENCE="${IMAGE_REFERENCE:-docker.io/${IMAGE_REPOSITORY}:${IMAGE_TAG}}"
NANO_BOT_MODEL="${NANO_BOT_MODEL:-minimax-m2.7}"
KBS_POLICY_NAME="${KBS_POLICY_NAME:-security-policy}"
KBS_POLICY_KEY="${KBS_POLICY_KEY:-test}"
KBS_PUBLIC_KEY_NAME="${KBS_PUBLIC_KEY_NAME:-sig-public-key}"
KBS_PUBLIC_KEY_KEY="${KBS_PUBLIC_KEY_KEY:-test}"
KEEP_KBS="${KEEP_KBS:-1}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*"; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 1; }; }

cleanup() {
  local status=$?
  if [[ "$KEEP_KBS" != "1" ]] && "$CONTAINER_ENGINE" container inspect "$KBS_CONTAINER_NAME" >/dev/null 2>&1; then
    "$CONTAINER_ENGINE" rm -f "$KBS_CONTAINER_NAME" >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

need_cmd "$CONTAINER_ENGINE"
need_cmd cosign
need_cmd skopeo
need_cmd jq

if ! "$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$COCO_CONTAINER_NAME"; then
  err "CoCo container is not running: $COCO_CONTAINER_NAME"
  exit 1
fi

registry_running() {
  local registry_name
  for registry_name in "${LOCAL_REGISTRY_NAME:-}" nano-bot-local-registry coco-local-registry; do
    if [[ -n "$registry_name" ]] && "$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$registry_name"; then
      return 0
    fi
  done
  return 1
}

if ! registry_running; then
  err "Local registry is not running. Start it first or run the normal nano_bot flow once."
  exit 1
fi

if [[ -z "$KBS_GUEST_HOST" ]]; then
  KBS_GUEST_HOST="$($CONTAINER_ENGINE inspect "$COCO_CONTAINER_NAME" --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' | head -1)"
fi
if [[ -z "$KBS_GUEST_HOST" ]]; then
  err "Unable to determine the Docker bridge gateway used by the CoCo container."
  exit 1
fi

mkdir -p "$SIGNED_IMAGES_STATE_DIR/repository/default/$KBS_PUBLIC_KEY_NAME"
mkdir -p "$SIGNED_IMAGES_STATE_DIR/repository/default/$KBS_POLICY_NAME"
chmod 700 "$SIGNED_IMAGES_STATE_DIR"

COSIGN_KEY="$SIGNED_IMAGES_STATE_DIR/cosign.key"
COSIGN_PUBLIC_KEY="$SIGNED_IMAGES_STATE_DIR/cosign.pub"
KBS_AUTH_KEY="$SIGNED_IMAGES_STATE_DIR/kbs-auth-key.pem"
KBS_AUTH_PUBLIC_KEY="$SIGNED_IMAGES_STATE_DIR/kbs-auth-pub.pem"
KBS_CONFIG="$SIGNED_IMAGES_STATE_DIR/kbs-config.toml"

if [[ ! -f "$COSIGN_KEY" || ! -f "$COSIGN_PUBLIC_KEY" ]]; then
  log "Generating cosign key pair in $SIGNED_IMAGES_STATE_DIR."
  (umask 077; COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign generate-key-pair)
  mv -f cosign.key "$COSIGN_KEY"
  mv -f cosign.pub "$COSIGN_PUBLIC_KEY"
fi

if [[ ! -f "$KBS_AUTH_KEY" || ! -f "$KBS_AUTH_PUBLIC_KEY" ]]; then
  log "Generating the local KBS admin authentication key pair."
  openssl genpkey -algorithm ed25519 -out "$KBS_AUTH_KEY"
  openssl pkey -in "$KBS_AUTH_KEY" -pubout -out "$KBS_AUTH_PUBLIC_KEY"
  chmod 600 "$KBS_AUTH_KEY"
fi

IMAGE_DIGEST="$(skopeo inspect --tls-verify=false "docker://${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_REPOSITORY}:${IMAGE_TAG}" | jq -er '.Digest')"
LOCAL_IMAGE_DIGEST="${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_REPOSITORY}@${IMAGE_DIGEST}"
log "Signing ${LOCAL_IMAGE_DIGEST}."
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign sign --allow-insecure-registry --key "$COSIGN_KEY" --tlog-upload=false --yes "$LOCAL_IMAGE_DIGEST"

log "Verifying the registry signature."
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign verify --allow-insecure-registry --insecure-ignore-tlog --key "$COSIGN_PUBLIC_KEY" "$LOCAL_IMAGE_DIGEST" >/dev/null

cp -f "$COSIGN_PUBLIC_KEY" "$SIGNED_IMAGES_STATE_DIR/repository/default/$KBS_PUBLIC_KEY_NAME/$KBS_PUBLIC_KEY_KEY"
cat > "$SIGNED_IMAGES_STATE_DIR/repository/default/$KBS_POLICY_NAME/$KBS_POLICY_KEY" <<EOF
{
  "default": [
    { "type": "reject" }
  ],
  "transports": {
    "docker": {
      "docker.io/${IMAGE_REPOSITORY}": [
        {
          "type": "sigstoreSigned",
          "keyPath": "kbs:///default/${KBS_PUBLIC_KEY_NAME}/${KBS_PUBLIC_KEY_KEY}"
        }
      ]
    }
  }
}
EOF

cat > "$KBS_CONFIG" <<EOF
[http_server]
sockets = ["0.0.0.0:${KBS_PORT}"]
insecure_http = true

[attestation_token]
insecure_key = true

[attestation_service]
type = "coco_as_builtin"
work_dir = "/opt/confidential-containers/attestation-service"

[attestation_service.attestation_token_broker]
type = "Ear"
duration_min = 5

[attestation_service.rvps_config]
type = "BuiltIn"

[admin]
auth_public_key = "/opt/confidential-containers/kbs/user-keys/kbs-auth-pub.pem"

[[plugins]]
name = "resource"
type = "LocalFs"
dir_path = "/opt/confidential-containers/kbs/repository"
EOF

if "$CONTAINER_ENGINE" container inspect "$KBS_CONTAINER_NAME" >/dev/null 2>&1; then
  if ! "$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$KBS_CONTAINER_NAME"; then
    "$CONTAINER_ENGINE" start "$KBS_CONTAINER_NAME" >/dev/null
  fi
else
  log "Starting Trustee KBS on host port ${KBS_PORT}."
  "$CONTAINER_ENGINE" run -d --name "$KBS_CONTAINER_NAME" --network host \
    -v "$KBS_CONFIG:/etc/kbs/kbs-config.toml:ro" \
    -v "$SIGNED_IMAGES_STATE_DIR/repository:/opt/confidential-containers/kbs/repository:ro" \
    -v "$KBS_AUTH_PUBLIC_KEY:/opt/confidential-containers/kbs/user-keys/kbs-auth-pub.pem:ro" \
    -v /etc/hosts:/etc/hosts:ro \
    "$KBS_IMAGE" /usr/local/bin/kbs --config-file /etc/kbs/kbs-config.toml >/dev/null
fi

for attempt in $(seq 1 30); do
  if curl -fsS --max-time 2 "http://127.0.0.1:${KBS_PORT}/" >/dev/null 2>&1 || curl -sS --max-time 2 "http://127.0.0.1:${KBS_PORT}/" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" == 30 ]]; then
    err "Trustee KBS did not listen on 127.0.0.1:${KBS_PORT}."
    "$CONTAINER_ENGINE" logs --tail 80 "$KBS_CONTAINER_NAME" >&2 || true
    exit 1
  fi
  sleep 1
done

SIGNED_IMAGES_KBS_URL="http://${KBS_GUEST_HOST}:${KBS_PORT}"
SIGNED_IMAGES_POLICY="kbs:///default/${KBS_POLICY_NAME}/${KBS_POLICY_KEY}"
log "KBS is reachable on host port ${KBS_PORT}; guest URL is ${SIGNED_IMAGES_KBS_URL}."
log "Policy resource: ${SIGNED_IMAGES_POLICY}"
log "Running the complete signed-image CoCo + TDX flow."

SIGNED_IMAGES_ENABLED=1 \
SIGNED_IMAGES_KBS_URL="$SIGNED_IMAGES_KBS_URL" \
SIGNED_IMAGES_POLICY="$SIGNED_IMAGES_POLICY" \
IMAGE_METADATA_VALIDATION=1 \
IMAGE_METADATA_INSPECT_REFERENCE="${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_REPOSITORY}:${IMAGE_TAG}" \
IMAGE_METADATA_EXPECTED_DIGEST="$IMAGE_DIGEST" \
IMAGE_METADATA_COSIGN_KEY="$COSIGN_PUBLIC_KEY" \
NANO_BOT_IMAGE="$IMAGE_REFERENCE" \
NANO_BOT_MODEL="$NANO_BOT_MODEL" \
USE_LOCAL_REGISTRY=0 \
RESTART_CONTAINERD="${RESTART_CONTAINERD:-0}" \
CONTAINER_NAME="$COCO_CONTAINER_NAME" \
  "$REPRO_SCRIPT"

log "Signed-image workload completed successfully."
log "Public key: $COSIGN_PUBLIC_KEY"
log "Image digest: $IMAGE_REFERENCE@$IMAGE_DIGEST"

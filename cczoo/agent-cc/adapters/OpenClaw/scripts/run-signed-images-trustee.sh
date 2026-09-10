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

# Sign an OpenClaw image, publish its verification policy through Trustee KBS,
# and deploy it with guest-side verification in the existing CoCo TDX runtime.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LAUNCHER="$SCRIPT_DIR/run-coco-tdx.sh"

CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
COCO_CONTAINER="${COCO_CONTAINER:-asterinas-coco-tdx}"
KBS_CONTAINER="${KBS_CONTAINER:-openclaw-trustee-kbs}"
KBS_IMAGE="${KBS_IMAGE:-ghcr.io/confidential-containers/staged-images/kbs:c96dbe6bcc3d7529fdb27afb19a54a6625b29634}"
KBS_PORT="${KBS_PORT:-8080}"
KBS_GUEST_HOST="${KBS_GUEST_HOST:-}"
STATE_DIR="${OPENCLAW_TRUST_STATE_DIR:-$HOME/.config/openclaw-coco-trust}"
REGISTRY_HOST="${REGISTRY_HOST:-127.0.0.1}"
REGISTRY_PORT="${REGISTRY_PORT:-5000}"
IMAGE_REPOSITORY="${IMAGE_REPOSITORY:-library/openclaw-coco-tdx}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
GUEST_IMAGE="${OPENCLAW_IMAGE:-docker.io/${IMAGE_REPOSITORY}:${IMAGE_TAG}}"
POLICY_RESOURCE="${POLICY_RESOURCE:-security-policy/openclaw}"
PUBLIC_KEY_RESOURCE="${PUBLIC_KEY_RESOURCE:-sig-public-key/openclaw}"
KATA_CONFIG="${KATA_CONFIG:-/opt/coco/config/configuration-qemu-tdx-linux.toml}"
SIGNED_KATA_CONFIG="${SIGNED_KATA_CONFIG:-/opt/coco/config/configuration-qemu-tdx-linux-signed.toml}"
SIGNED_RUNTIME_CLASS="${SIGNED_RUNTIME_CLASS:-kata-qemu-tdx-linux-signed}"
CONTAINERD_SNIPPET="${CONTAINERD_SNIPPET:-/etc/containerd/conf.d/61-kata-qemu-tdx-linux-signed.toml}"

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }
need_cmd() { command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"; }

for command_name in "$CONTAINER_ENGINE" cosign skopeo jq curl openssl; do
  need_cmd "$command_name"
done
[[ "$POLICY_RESOURCE" == */* ]] || fail "POLICY_RESOURCE must be NAME/KEY"
[[ "$PUBLIC_KEY_RESOURCE" == */* ]] || fail "PUBLIC_KEY_RESOURCE must be NAME/KEY"
"$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$COCO_CONTAINER" ||
  fail "CoCo container is not running: $COCO_CONTAINER"

if [[ -z "$KBS_GUEST_HOST" ]]; then
  KBS_GUEST_HOST="$($CONTAINER_ENGINE inspect "$COCO_CONTAINER" --format '{{range .NetworkSettings.Networks}}{{.Gateway}}{{end}}' | head -1)"
fi
[[ -n "$KBS_GUEST_HOST" ]] || fail "could not determine the host address visible from the CoCo network"

info "Installing the dedicated Kata guest-pull runtime $SIGNED_RUNTIME_CLASS."
"$CONTAINER_ENGINE" exec "$COCO_CONTAINER" cp -f "$KATA_CONFIG" "$SIGNED_KATA_CONFIG"
"$CONTAINER_ENGINE" exec "$COCO_CONTAINER" sed -i \
  's/^experimental_force_guest_pull = true$/experimental_force_guest_pull = false/' "$KATA_CONFIG"
"$CONTAINER_ENGINE" exec "$COCO_CONTAINER" sed -i \
  's/^experimental_force_guest_pull = false$/experimental_force_guest_pull = true/' "$SIGNED_KATA_CONFIG"
"$CONTAINER_ENGINE" exec "$COCO_CONTAINER" grep -q '^experimental_force_guest_pull = true$' "$SIGNED_KATA_CONFIG" ||
  fail "could not enable experimental_force_guest_pull in $SIGNED_KATA_CONFIG"

"$CONTAINER_ENGINE" exec -i "$COCO_CONTAINER" sh -c "cat > '$CONTAINERD_SNIPPET'" <<EOF
[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.${SIGNED_RUNTIME_CLASS}]
runtime_type = "io.containerd.kata-qemu-tdx.v2"
runtime_path = "/opt/coco/prebuilt/asterinas-coco/containerd-shim-kata-v2"
pod_annotations = ["io.katacontainers.*"]
privileged_without_host_devices = true
snapshotter = "native"

[plugins."io.containerd.cri.v1.runtime".containerd.runtimes.${SIGNED_RUNTIME_CLASS}.options]
ConfigPath = "${SIGNED_KATA_CONFIG}"

[plugins."io.containerd.cri.v1.images".runtime_platforms.${SIGNED_RUNTIME_CLASS}]
snapshotter = "native"
EOF

"$CONTAINER_ENGINE" exec \
  -e HTTP_PROXY="${OPENCLAW_PROXY_URL:-}" \
  -e HTTPS_PROXY="${OPENCLAW_PROXY_URL:-}" \
  -e http_proxy="${OPENCLAW_PROXY_URL:-}" \
  -e https_proxy="${OPENCLAW_PROXY_URL:-}" \
  "$COCO_CONTAINER" bash -lc \
  'pkill -x containerd || true; nohup containerd >/tmp/containerd.out 2>/tmp/containerd.err &'
for attempt in $(seq 1 30); do
  if "$CONTAINER_ENGINE" exec "$COCO_CONTAINER" ctr version >/dev/null 2>&1; then
    break
  fi
  [[ "$attempt" != 30 ]] || fail "containerd did not become ready after installing the signed runtime"
  sleep 1
done
"$CONTAINER_ENGINE" exec "$COCO_CONTAINER" mkdir -p /var/lib/containerd/tmpmounts
"$CONTAINER_ENGINE" exec -i -e KUBECONFIG=/etc/kubernetes/super-admin.conf "$COCO_CONTAINER" \
  kubectl apply -f - <<EOF
apiVersion: node.k8s.io/v1
kind: RuntimeClass
metadata:
  name: ${SIGNED_RUNTIME_CLASS}
handler: ${SIGNED_RUNTIME_CLASS}
EOF

policy_name="${POLICY_RESOURCE%/*}"
policy_key="${POLICY_RESOURCE#*/}"
public_key_name="${PUBLIC_KEY_RESOURCE%/*}"
public_key_key="${PUBLIC_KEY_RESOURCE#*/}"
repository_dir="$STATE_DIR/repository/default"
mkdir -p "$repository_dir/$policy_name" "$repository_dir/$public_key_name"
chmod 700 "$STATE_DIR"

cosign_key="$STATE_DIR/cosign.key"
cosign_public_key="$STATE_DIR/cosign.pub"
kbs_auth_key="$STATE_DIR/kbs-auth-key.pem"
kbs_auth_public_key="$STATE_DIR/kbs-auth-pub.pem"
kbs_config="$STATE_DIR/kbs-config.toml"

if [[ ! -f "$cosign_key" || ! -f "$cosign_public_key" ]]; then
  info "Generating the image-signing key pair under $STATE_DIR."
  (cd "$STATE_DIR" && umask 077 && COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign generate-key-pair)
fi
if [[ ! -f "$kbs_auth_key" || ! -f "$kbs_auth_public_key" ]]; then
  info "Generating the Trustee administrator authentication key pair."
  openssl genpkey -algorithm ed25519 -out "$kbs_auth_key"
  openssl pkey -in "$kbs_auth_key" -pubout -out "$kbs_auth_public_key"
  chmod 600 "$kbs_auth_key"
fi

registry_image="${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_REPOSITORY}:${IMAGE_TAG}"
image_digest="$(skopeo inspect --tls-verify=false "docker://$registry_image" | jq -er '.Digest')"
digest_reference="${REGISTRY_HOST}:${REGISTRY_PORT}/${IMAGE_REPOSITORY}@${image_digest}"
info "Signing OpenClaw image digest $image_digest."
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign sign --allow-insecure-registry \
  --key "$cosign_key" --tlog-upload=false --yes "$digest_reference"
COSIGN_PASSWORD="${COSIGN_PASSWORD:-}" cosign verify --allow-insecure-registry \
  --insecure-ignore-tlog --key "$cosign_public_key" "$digest_reference" >/dev/null

cp -f "$cosign_public_key" "$repository_dir/$public_key_name/$public_key_key"
cat >"$repository_dir/$policy_name/$policy_key" <<EOF
{
  "default": [{ "type": "reject" }],
  "transports": {
    "docker": {
      "docker.io/${IMAGE_REPOSITORY}": [{
        "type": "sigstoreSigned",
        "keyPath": "kbs:///default/${PUBLIC_KEY_RESOURCE}"
      }]
    }
  }
}
EOF

cat >"$kbs_config" <<EOF
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

if "$CONTAINER_ENGINE" container inspect "$KBS_CONTAINER" >/dev/null 2>&1; then
  "$CONTAINER_ENGINE" rm -f "$KBS_CONTAINER" >/dev/null
fi
info "Starting Trustee KBS on host port $KBS_PORT."
kbs_started_at="$(date --iso-8601=seconds)"
"$CONTAINER_ENGINE" run -d --name "$KBS_CONTAINER" --network host \
  -v "$kbs_config:/etc/kbs/kbs-config.toml:ro" \
  -v "$repository_dir:/opt/confidential-containers/kbs/repository" \
  -v "$kbs_auth_public_key:/opt/confidential-containers/kbs/user-keys/kbs-auth-pub.pem:ro" \
  -v /etc/hosts:/etc/hosts:ro \
  "$KBS_IMAGE" /usr/local/bin/kbs --config-file /etc/kbs/kbs-config.toml >/dev/null

for attempt in $(seq 1 30); do
  if curl -sS --max-time 2 "http://127.0.0.1:${KBS_PORT}/" >/dev/null 2>&1; then
    break
  fi
  [[ "$attempt" != 30 ]] || fail "Trustee KBS did not listen on port $KBS_PORT"
  sleep 1
done

kbs_url="http://${KBS_GUEST_HOST}:${KBS_PORT}"
image_policy="kbs:///default/${POLICY_RESOURCE}"
info "Deploying $GUEST_IMAGE with guest-side signature verification."
"$CONTAINER_ENGINE" exec -i \
  -e KUBECONFIG=/etc/kubernetes/super-admin.conf \
  -e OPENCLAW_PROXY_URL="${OPENCLAW_PROXY_URL:-}" \
  "$COCO_CONTAINER" bash -s -- \
  --image "$GUEST_IMAGE" \
  --runtime-class "$SIGNED_RUNTIME_CLASS" \
  --api-secret "${OPENCLAW_API_SECRET:-agent-api-key}" \
  --gateway-secret "${OPENCLAW_GATEWAY_SECRET:-openclaw-gateway-token}" \
  --model "${OPENCLAW_MODEL:-openrouter/nvidia/nemotron-3.5-lightning:free}" \
  --signed-images \
  --kbs-url "$kbs_url" \
  --image-policy "$image_policy" \
  --delete <"$LAUNCHER"

if ! "$CONTAINER_ENGINE" logs --since "$kbs_started_at" "$KBS_CONTAINER" 2>&1 |
  grep -Eq '"(GET|POST) /(kbs|resource|attest|auth|token)(/|\?| )'; then
  fail "Pod became ready, but Trustee received no guest attestation or resource request; signed-image enforcement is not active in this guest image"
fi

info "Signed OpenClaw image deployed at digest $image_digest."
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

set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

usage() {
    cat <<'EOF'
Usage: run_openai_workload.sh [options]

Run this script inside the official Asterinas CoCo container. It never accepts
or prints an API key; the key must already exist in the selected Kubernetes
cluster as a Secret.

Options:
  --image IMAGE             Guest image reference (default: docker.io/library/nano_bot:2.0)
  --secret NAME             Secret containing OPENAI_API_KEY (default: nano-bot-api-key)
  --model-config FILE       Provider profile with MODEL_* settings
  --api-address URL         OpenAI-compatible base URL (default: https://openrouter.ai/api/v1)
  --model NAME              Model name (default: minimax/minimax-m3:free)
  --proxy URL               Workload HTTP(S) proxy, guest-resolvable
  --no-proxy LIST           Workload no_proxy value
  --namespace NAME          Kubernetes namespace (default: default)
  --node-name NAME          Pin the Pod to a node (optional)
  --tmpfs-size SIZE         containerd tmpmount size (default: 2G)
  --nydus-size SIZE         Nydus temporary storage size (default: 2G)
  --help                    Show this help
EOF
}

IMAGE_REF="${IMAGE_REF:-docker.io/library/nano_bot:2.0}"
SECRET_NAME="${SECRET_NAME:-nano-bot-api-key}"
API_ADDRESS="${MODEL_API_ADDRESS:-${OPENAI_API_ADDRESS:-https://openrouter.ai/api/v1}}"
MODEL="${MODEL_NAME:-${NANO_BOT_MODEL:-minimax/minimax-m3:free}}"
PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}"
NO_PROXY_VALUE="${NO_PROXY_VALUE:-127.0.0.1,localhost,10.244.0.0/16,10.96.0.0/12}"
FARADAY_SSL_VERIFY="${FARADAY_SSL_VERIFY:-none}"
TMPFS_SIZE="${TMPFS_SIZE:-2G}"
NYDUS_SIZE="${NYDUS_SIZE:-2G}"
POD_NAME="${POD_NAME:-openai-workload-kata-qemu-tdx}"
RUNTIME_CLASS="${RUNTIME_CLASS:-kata-qemu-tdx-linux}"
NAMESPACE="${NAMESPACE:-default}"
NODE_NAME="${NODE_NAME:-}"
KUBECTL="${KUBECTL:-kubectl}"
MODEL_CONFIG="${MODEL_CONFIG:-}"

load_model_config() {
  local config_file="$1" key value
  [[ -r "$config_file" ]] || fail "model config is not readable: $config_file"
  while IFS='=' read -r key value || [[ -n "$key" ]]; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    value="${value%$'\r'}"
    case "$key" in
      MODEL_API_ADDRESS) API_ADDRESS="$value" ;;
      MODEL_NAME) MODEL="$value" ;;
      MODEL_API_KEY_SECRET) SECRET_NAME="$value" ;;
      MODEL_API_KEY_SECRET_KEY) SECRET_KEY="$value" ;;
      MODEL_PROXY_URL) PROXY_URL="$value" ;;
      MODEL_NO_PROXY) NO_PROXY_VALUE="$value" ;;
      MODEL_TLS_VERIFY) FARADAY_SSL_VERIFY="$value" ;;
      *) fail "unsupported model config key: $key" ;;
    esac
  done <"$config_file"
}

SECRET_KEY="${MODEL_API_KEY_SECRET_KEY:-OPENAI_API_KEY}"
if (($#)); then
  for ((config_index = 1; config_index <= $#; config_index++)); do
    if [[ "${!config_index}" == "--model-config" ]]; then
      next_index=$((config_index + 1))
      [[ $next_index -le $# ]] || fail "--model-config requires a file"
      MODEL_CONFIG="${!next_index}"
    fi
  done
fi
[[ -z "$MODEL_CONFIG" ]] || load_model_config "$MODEL_CONFIG"

while (($#)); do
    case "$1" in
        --image) IMAGE_REF="$2"; shift 2 ;;
        --secret) SECRET_NAME="$2"; shift 2 ;;
        --model-config) shift 2 ;;
        --api-address) API_ADDRESS="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --proxy) PROXY_URL="$2"; shift 2 ;;
        --no-proxy) NO_PROXY_VALUE="$2"; shift 2 ;;
        --namespace) NAMESPACE="$2"; shift 2 ;;
        --node-name) NODE_NAME="$2"; shift 2 ;;
        --tmpfs-size) TMPFS_SIZE="$2"; shift 2 ;;
        --nydus-size) NYDUS_SIZE="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

[[ -n "$IMAGE_REF" && -n "$API_ADDRESS" && -n "$MODEL" && -n "$NAMESPACE" ]] || fail "image, API address, model, and namespace must be non-empty"
[[ "$IMAGE_REF" == */*:* ]] || fail "image must include a repository and tag: $IMAGE_REF"
[[ "$API_ADDRESS" != *$'\n'* && "$PROXY_URL" != *$'\n'* && "$MODEL" != *$'\n'* && "$NAMESPACE" != *$'\n'* && "$NODE_NAME" != *$'\n'* ]] || fail "values must not contain newlines"
command -v "$KUBECTL" >/dev/null || fail "kubectl is not available"
[[ "$(id -u)" == 0 ]] || fail "run inside the privileged CoCo container as root"

info "Kubernetes context: $($KUBECTL config current-context 2>/dev/null || echo unknown)"
[[ "$($KUBECTL get runtimeclass "$RUNTIME_CLASS" -o name 2>/dev/null)" == *"$RUNTIME_CLASS" ]] || \
    fail "RuntimeClass $RUNTIME_CLASS is not available in this Kubernetes cluster"
[[ "$($KUBECTL get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.metadata.name}' 2>/dev/null)" == "$SECRET_NAME" ]] || \
    fail "Secret $SECRET_NAME is not available in this Kubernetes cluster"

ensure_tmpfs() {
    local path=$1 size=$2
    mkdir -p "$path"
    if mountpoint -q "$path"; then
        mount -o "remount,size=$size" "$path" || fail "cannot resize $path"
    else
        mount -t tmpfs -o "rw,size=$size" tmpfs "$path" || fail "cannot mount $path"
    fi
    info "$(findmnt -no TARGET,FSTYPE,OPTIONS "$path")"
}

ensure_tmpfs /var/lib/containerd/tmpmounts "$TMPFS_SIZE"
ensure_tmpfs /var/lib/containerd-nydus "$NYDUS_SIZE"

INITRD="${INITRD:-/opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img}"
[[ -r "$INITRD" ]] || fail "Asterinas initramfs not found: $INITRD"
workdir=""
manifest=""
workdir=$(mktemp -d)
trap 'rm -rf "$workdir" "$manifest"' EXIT
gzip -dc "$INITRD" | cpio -idmu --quiet -D "$workdir" || fail "cannot inspect initramfs"
mirror=$(sed -n 's/^[[:space:]]*location[[:space:]]*=[[:space:]]*"\([^"]*\)"/\1/p' "$workdir/etc/registry-configuration.toml" 2>/dev/null | tail -1 || true)
[[ -n "$mirror" ]] || fail "initramfs has no registry mirror configuration"
info "Guest registry mirror: $mirror"

containerd_pid=$(pgrep -f '^/usr/bin/containerd( |$)' | head -1 || true)
if [[ -n "$containerd_pid" ]]; then
  containerd_no_proxy=$(tr '\0' '\n' < "/proc/$containerd_pid/environ" | awk -F= '$1 == "NO_PROXY" || $1 == "no_proxy" {print $2; exit}')
  if [[ -n "$PROXY_URL" && -z "$containerd_no_proxy" ]]; then
    fail "containerd has an outbound proxy but no NO_PROXY; restart it with the registry and cluster networks bypassed"
  fi
fi

if [[ -n "$PROXY_URL" ]]; then
    proxy_env=$(cat <<EOF
        - name: HTTP_PROXY
          value: "$PROXY_URL"
        - name: HTTPS_PROXY
          value: "$PROXY_URL"
        - name: http_proxy
          value: "$PROXY_URL"
        - name: https_proxy
          value: "$PROXY_URL"
EOF
    )
else
    proxy_env=""
    info "No workload proxy supplied; API access must work directly from the guest"
fi

manifest=$(mktemp)
cat > "$manifest" <<EOF
apiVersion: v1
kind: Pod
metadata:
  name: $POD_NAME
  namespace: $NAMESPACE
  labels:
    app: openai-workload
spec:
  runtimeClassName: $RUNTIME_CLASS
  restartPolicy: Never
  containers:
    - name: openai-workload
      image: $IMAGE_REF
      imagePullPolicy: Always
      command: ["sleep", "infinity"]
      env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: $SECRET_NAME
              key: $SECRET_KEY
        - name: OPENAI_API_ADDRESS
          value: "$API_ADDRESS"
        - name: NANO_BOT_MODEL
          value: "$MODEL"
        - name: FARADAY_SSL_VERIFY
          value: "none"
$proxy_env
        - name: NO_PROXY
          value: "$NO_PROXY_VALUE"
        - name: no_proxy
          value: "$NO_PROXY_VALUE"
EOF

if [[ -n "$NODE_NAME" ]]; then
  sed -i "/^  runtimeClassName:/a\\  nodeName: $NODE_NAME" "$manifest"
fi

$KUBECTL delete pod "$POD_NAME" -n "$NAMESPACE" --ignore-not-found --wait=true >/dev/null
$KUBECTL apply -f "$manifest"
if ! $KUBECTL wait --for=condition=Ready "pod/$POD_NAME" -n "$NAMESPACE" --timeout=10m; then
  $KUBECTL describe pod "$POD_NAME" -n "$NAMESPACE" | sed -n '/^Events:/,$p' >&2 || true
    exit 1
fi
$KUBECTL get pod "$POD_NAME" -n "$NAMESPACE" -o wide
info "Run the chat probe with:"
info "  printf 'Your message\\nquit\\n' | $KUBECTL exec -n $NAMESPACE -i $POD_NAME -- /usr/local/bin/tdx-chat-bot.rb"
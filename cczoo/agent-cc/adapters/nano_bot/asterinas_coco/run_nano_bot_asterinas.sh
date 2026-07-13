#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'EOF'
Usage: run_nano_bot_asterinas.sh [options]

Run this script inside the official Asterinas CoCo container. It never accepts
or prints an API key; the key must already exist in the selected Kubernetes
cluster as a Secret.

Options:
  --image IMAGE             Guest image reference (default: docker.io/library/nano_bot:2.0)
  --secret NAME             Secret containing OPENAI_API_KEY (default: nano-bot-api-key)
  --api-address URL         OpenAI-compatible base URL (default: https://aidemo.intel.cn/v1)
  --model NAME              Model name (default: minimax-m2.7)
  --proxy URL               Workload HTTP(S) proxy, for example http://10.0.0.5:913
  --no-proxy LIST           Workload no_proxy value
  --tmpfs-size SIZE         containerd tmpmount size (default: 2G)
  --nydus-size SIZE         Nydus temporary storage size (default: 2G)
  --help                    Show this help
EOF
}

IMAGE_REF="${IMAGE_REF:-docker.io/library/nano_bot:2.0}"
SECRET_NAME="${SECRET_NAME:-nano-bot-api-key}"
API_ADDRESS="${OPENAI_API_ADDRESS:-https://aidemo.intel.cn/v1}"
MODEL="${NANO_BOT_MODEL:-minimax-m2.7}"
PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}"
NO_PROXY_VALUE="${NO_PROXY_VALUE:-127.0.0.1,localhost,10.244.0.0/16,10.96.0.0/12}"
TMPFS_SIZE="${TMPFS_SIZE:-2G}"
NYDUS_SIZE="${NYDUS_SIZE:-2G}"
POD_NAME="${POD_NAME:-nano-bot-kata-qemu-tdx-asterinas}"
RUNTIME_CLASS="${RUNTIME_CLASS:-kata-qemu-tdx-asterinas}"
KUBECTL="${KUBECTL:-kubectl}"

while (($#)); do
    case "$1" in
        --image) IMAGE_REF="$2"; shift 2 ;;
        --secret) SECRET_NAME="$2"; shift 2 ;;
        --api-address) API_ADDRESS="$2"; shift 2 ;;
        --model) MODEL="$2"; shift 2 ;;
        --proxy) PROXY_URL="$2"; shift 2 ;;
        --no-proxy) NO_PROXY_VALUE="$2"; shift 2 ;;
        --tmpfs-size) TMPFS_SIZE="$2"; shift 2 ;;
        --nydus-size) NYDUS_SIZE="$2"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
    esac
done

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

[[ -n "$IMAGE_REF" && -n "$API_ADDRESS" && -n "$MODEL" ]] || fail "image, API address, and model must be non-empty"
[[ "$IMAGE_REF" == */*:* ]] || fail "image must include a repository and tag: $IMAGE_REF"
[[ "$API_ADDRESS" != *$'\n'* && "$PROXY_URL" != *$'\n'* ]] || fail "URLs must not contain newlines"
command -v "$KUBECTL" >/dev/null || fail "kubectl is not available"
[[ "$(id -u)" == 0 ]] || fail "run inside the privileged CoCo container as root"

info "Kubernetes context: $($KUBECTL config current-context 2>/dev/null || echo unknown)"
[[ "$($KUBECTL get runtimeclass "$RUNTIME_CLASS" -o name 2>/dev/null)" == *"$RUNTIME_CLASS" ]] || \
    fail "RuntimeClass $RUNTIME_CLASS is not available in this Kubernetes cluster"
[[ "$($KUBECTL get secret "$SECRET_NAME" -o jsonpath='{.metadata.name}' 2>/dev/null)" == "$SECRET_NAME" ]] || \
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
  labels:
    app: nano-bot
spec:
  runtimeClassName: $RUNTIME_CLASS
  restartPolicy: Never
  containers:
    - name: nano-bot
      image: $IMAGE_REF
      imagePullPolicy: Always
      command: ["sleep", "infinity"]
      env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: $SECRET_NAME
              key: OPENAI_API_KEY
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

$KUBECTL delete pod "$POD_NAME" --ignore-not-found --wait=true >/dev/null
$KUBECTL apply -f "$manifest"
if ! $KUBECTL wait --for=condition=Ready "pod/$POD_NAME" --timeout=10m; then
    $KUBECTL describe pod "$POD_NAME" | sed -n '/^Events:/,$p' >&2 || true
    exit 1
fi
$KUBECTL get pod "$POD_NAME" -o wide
info "Run the chat probe with:"
info "  printf 'Your message\\nquit\\n' | $KUBECTL exec -i $POD_NAME -- /usr/local/bin/tdx-chat-bot.rb"
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

# End-to-end automation for: CoCo (Confidential Containers) + Intel TDX +
# a Linux guest kernel + the nano_bot chat workload, running as the actual
# payload container inside the TDX confidential guest VM.
#
# This script does NOT contain (and must never contain) any secret,
# credential, or environment-specific network detail (proxy URL, API key,
# internal hostnames). Everything like that is supplied by the caller via
# environment variables - see README.md for the full list and examples.
#
# It builds on top of an existing, already-working CoCo/Kata/TDX/QEMU stack
# (see the linux-coco-tdx sibling project this was derived from) that
# replaces the reference Asterinas guest kernel with a self-compiled Linux
# kernel. This script does not modify the original Asterinas runtime TOML,
# manifest, or initrd - it creates Linux-specific, independently namespaced
# copies of everything.

# ---------------------------------------------------------------------------
# Container / Pod identity
# ---------------------------------------------------------------------------
CONTAINER_NAME="${CONTAINER_NAME:-asterinas-coco-tdx}"
POD_NAME="${POD_NAME:-nano-bot-kata-qemu-tdx-linux}"
WAIT_TIMEOUT="${WAIT_TIMEOUT:-600s}"
CONTAINER_ENGINE="${CONTAINER_ENGINE:-docker}"
CONTAINER_KUBECONFIG="${CONTAINER_KUBECONFIG:-/etc/kubernetes/super-admin.conf}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# ---------------------------------------------------------------------------
# Local files (in this repository)
# ---------------------------------------------------------------------------
LOCAL_RUNTIMECLASS="${LOCAL_RUNTIMECLASS:-$ROOT_DIR/manifests/runtimeclass-kata-qemu-tdx-linux.yaml}"
LOCAL_CONTAINERD_SNIPPET="${LOCAL_CONTAINERD_SNIPPET:-$ROOT_DIR/config/containerd-60-linux-coco-tdx.toml}"
LOCAL_KERNEL_PARAMS_FILE="${LOCAL_KERNEL_PARAMS_FILE:-$ROOT_DIR/config/kernel-params-linux.txt}"

# ---------------------------------------------------------------------------
# Container-side paths (can be overridden by environment)
# ---------------------------------------------------------------------------
CONTAINER_MANIFEST="${CONTAINER_MANIFEST:-/opt/coco/manifests/nano-bot-kata-qemu-tdx-linux.yaml}"
CONTAINER_RUNTIMECLASS="${CONTAINER_RUNTIMECLASS:-/opt/coco/manifests/runtimeclass-kata-qemu-tdx-linux.yaml}"
CONTAINER_CONTAINERD_SNIPPET="${CONTAINER_CONTAINERD_SNIPPET:-/etc/containerd/conf.d/60-linux-coco-tdx.toml}"

# ---------------------------------------------------------------------------
# Runtime configuration paths (REQUIRED - environment-specific, not secrets,
# but there is no sane universal default so the script insists they be set)
# ---------------------------------------------------------------------------
SOURCE_RUNTIME_CFG="${SOURCE_RUNTIME_CFG:-}"
LINUX_RUNTIME_CFG="${LINUX_RUNTIME_CFG:-/opt/coco/config/configuration-qemu-tdx-linux.toml}"

HOST_LINUX_KERNEL="${HOST_LINUX_KERNEL:-}"
LINUX_KERNEL="${LINUX_KERNEL:-/opt/coco/prebuilt/linux-coco-tdx/vmlinuz-6.16.0-vsock-net-tdxguest-builtin}"

LINUX_INITRD="${LINUX_INITRD:-}"
LINUX_FIRMWARE="${LINUX_FIRMWARE:-/root/ovmf/release/OVMF.fd}"

# ---------------------------------------------------------------------------
# Networking - no environment-specific proxy or hostname is hardcoded here.
# If PROXY_URL is unset, the script will fall back to the common shell proxy
# variables so existing corp-network shells work without extra duplication.
# ---------------------------------------------------------------------------
PROXY_URL="${PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-${HTTP_PROXY:-${http_proxy:-}}}}}"
NO_PROXY_VALUE="${NO_PROXY_VALUE:-localhost,127.0.0.1,::1,10.96.0.0/12,10.244.0.0/16,10.88.0.0/16}"
ADD_HOST_ALIASES="${ADD_HOST_ALIASES:-1}"

# ---------------------------------------------------------------------------
# nano_bot / OpenAI-compatible API configuration - all required to be
# supplied explicitly by the caller, no environment-specific defaults.
# ---------------------------------------------------------------------------
OPENAI_API_ADDRESS="${OPENAI_API_ADDRESS:-}"
OPENAI_API_KEY="${OPENAI_API_KEY:-}"
API_KEY_SECRET_NAME="${API_KEY_SECRET_NAME:-nano-bot-api-key}"
API_KEY_SECRET_KEY="${API_KEY_SECRET_KEY:-OPENAI_API_KEY}"
NANO_BOT_MODEL="${NANO_BOT_MODEL:-gpt-3.5-turbo}"
FARADAY_SSL_VERIFY="${FARADAY_SSL_VERIFY:-}"
NANO_BOT_TEST_PROMPT="${NANO_BOT_TEST_PROMPT:-Reply with exactly: TDX guest connectivity confirmed.}"

# ---------------------------------------------------------------------------
# Image / local registry configuration
# ---------------------------------------------------------------------------
NANO_BOT_IMAGE="${NANO_BOT_IMAGE:-}"
USE_LOCAL_REGISTRY="${USE_LOCAL_REGISTRY:-1}"
IMAGE_NAME="${IMAGE_NAME:-nano_bot}"
IMAGE_TAG="${IMAGE_TAG:-1.0}"
FORCE_REBUILD_IMAGE="${FORCE_REBUILD_IMAGE:-0}"
FLATTEN_IMAGE="${FLATTEN_IMAGE:-1}"
IMAGE_PULL_POLICY="${IMAGE_PULL_POLICY:-IfNotPresent}"
PROBE_POD_NAME="${PROBE_POD_NAME:-${POD_NAME}-chat-once}"
PROBE_IMAGE="${PROBE_IMAGE:-}"
PROBE_IMAGE_PULL_POLICY="${PROBE_IMAGE_PULL_POLICY:-IfNotPresent}"
LOCAL_REGISTRY_NAME="${LOCAL_REGISTRY_NAME:-nano-bot-local-registry}"
LOCAL_REGISTRY_PORT="${LOCAL_REGISTRY_PORT:-5000}"
WORKLOAD_NODE_NAME="${WORKLOAD_NODE_NAME:-}"

# Signed-image verification is opt-in. When enabled, the KBS must already
# contain the public key and image policy referenced by these paths.
SIGNED_IMAGES_ENABLED="${SIGNED_IMAGES_ENABLED:-0}"
SIGNED_IMAGES_KBS_URL="${SIGNED_IMAGES_KBS_URL:-}"
SIGNED_IMAGES_POLICY="${SIGNED_IMAGES_POLICY:-}"
IMAGE_METADATA_VALIDATION="${IMAGE_METADATA_VALIDATION:-0}"
IMAGE_METADATA_INSPECT_REFERENCE="${IMAGE_METADATA_INSPECT_REFERENCE:-}"
IMAGE_METADATA_EXPECTED_DIGEST="${IMAGE_METADATA_EXPECTED_DIGEST:-}"
IMAGE_METADATA_COSIGN_KEY="${IMAGE_METADATA_COSIGN_KEY:-}"
IMAGE_METADATA_REPORT="${IMAGE_METADATA_REPORT:-/tmp/${POD_NAME}.image-metadata.json}"

# ---------------------------------------------------------------------------
# Feature flags
# ---------------------------------------------------------------------------
INSTALL_HANDLER="${INSTALL_HANDLER:-1}"
APPLY_RUNTIMECLASS="${APPLY_RUNTIMECLASS:-1}"
RESTART_CONTAINERD="${RESTART_CONTAINERD:-1}"
RUN_WORKLOAD="${RUN_WORKLOAD:-1}"
RUN_NANO_BOT_TEST="${RUN_NANO_BOT_TEST:-1}"
FORCE_RECREATE_LINUX_CFG="${FORCE_RECREATE_LINUX_CFG:-1}"

stamp() { date +"%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*"; }
err() { echo "[$(stamp)] ERROR: $*" >&2; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    err "Required command not found: $1"
    exit 1
  }
}

docker_exec() {
  "$CONTAINER_ENGINE" exec "$CONTAINER_NAME" env \
    -u http_proxy -u https_proxy -u HTTP_PROXY -u HTTPS_PROXY \
    KUBECONFIG="$CONTAINER_KUBECONFIG" \
    NO_PROXY="$NO_PROXY_VALUE" \
    no_proxy="$NO_PROXY_VALUE" \
    bash -lc "$*"
}

duration_to_seconds() {
  local duration="$1"

  case "$duration" in
    *ms)
      echo $(( ${duration%ms} / 1000 ))
      ;;
    *s)
      echo $(( ${duration%s} ))
      ;;
    *m)
      echo $(( ${duration%m} * 60 ))
      ;;
    *h)
      echo $(( ${duration%h} * 3600 ))
      ;;
    *)
      echo "$duration"
      ;;
  esac
}

wait_for_pod_absent() {
  local pod_name="$1"
  local timeout_seconds attempt

  timeout_seconds="$(duration_to_seconds "$WAIT_TIMEOUT")"
  if [[ "$timeout_seconds" -lt 1 ]]; then
    timeout_seconds=1
  fi

  for ((attempt = 0; attempt < timeout_seconds; attempt++)); do
    if ! docker_exec "kubectl get pod '$pod_name' >/dev/null 2>&1"; then
      return 0
    fi
    sleep 1
  done

  err "Timed out waiting for pod $pod_name to disappear after deletion."
  docker_exec "kubectl get pod '$pod_name' -o wide" || true
  return 1
}

recreate_pod_from_manifest() {
  local pod_name="$1"
  local manifest_path="$2"
  local force_delete="${3:-0}"
  local delete_flags="--ignore-not-found=true --wait=false"

  if docker_exec "kubectl get pod '$pod_name' >/dev/null 2>&1"; then
    log "Deleting existing pod $pod_name before re-creating it."
    if [[ "$force_delete" == "1" ]]; then
      delete_flags="$delete_flags --grace-period=0 --force"
    fi
    docker_exec "kubectl delete pod '$pod_name' $delete_flags >/dev/null 2>&1 || true"
    wait_for_pod_absent "$pod_name"
  fi

  docker_exec "kubectl apply -f '$manifest_path'"
}

# Derives the Linux guest kernel_params from whatever kernel_params the
# source (Asterinas) runtime config already has, rather than replacing them
# outright. Simply overwriting kernel_params with a short custom string
# drops required tokens (earlyprintk, agent.debug_console,
# agent.image_pull_timeout, cgroup_no_v1, systemd.unified_cgroup_hierarchy,
# etc.) and causes the guest's /init to fail almost immediately after boot
# (visible in the console log as an early, unexplained "reboot: Power down").
# We only:
#   - strip Asterinas/OSDK-specific tokens that don't apply to a Linux kernel
#     (ostd.log_level=..., aster.kernel_image=...)
#   - strip any existing agent.https_proxy/agent.no_proxy tokens (recomputed
#     below from PROXY_URL/NO_PROXY_VALUE so they always reflect what the
#     caller actually configured)
#   - prepend "ip=dhcp" and ensure "swiotlb=force"/"loglevel=3" are present
#     (needed for this Linux guest kernel build)
#   - append any extra tokens from $LOCAL_KERNEL_PARAMS_FILE, if present
kernel_params() {
  local src_params extra params
  src_params="$(docker_exec "grep -E '^kernel_params = ' '$SOURCE_RUNTIME_CFG'" 2>/dev/null     | sed -E 's/^kernel_params = "(.*)"$/\1/')"

  if [[ -z "$src_params" ]]; then
    err "Could not read kernel_params from $SOURCE_RUNTIME_CFG; using minimal defaults."
    src_params="console=ttyS0 earlyprintk=serial,ttyS0,115200 agent.debug_console agent.debug_console_vport=1026 agent.image_pull_timeout=3600 cgroup_no_v1=all systemd.unified_cgroup_hierarchy=1"
  fi

  # Strip tokens that are Asterinas/OSDK-specific or that we recompute below.
  params="$(printf '%s' "$src_params"     | sed -E 's/(^| )ostd\.log_level=[^ ]*/ /g; s/(^| )aster\.kernel_image=[^ ]*/ /g; s/(^| )agent\.https_proxy=[^ ]*/ /g; s/(^| )agent\.no_proxy=[^ ]*/ /g'     | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"

  # Ensure ip=dhcp, swiotlb=force, loglevel=3 are present.
  case " $params " in *" ip=dhcp "*) ;; *) params="ip=dhcp $params" ;; esac
  case " $params " in *" swiotlb=force "*) ;; *) params="$params swiotlb=force" ;; esac
  case " $params " in *" loglevel=3 "*) ;; *) params="$params loglevel=3" ;; esac

  if [[ -n "$PROXY_URL" ]]; then
    params="$params agent.https_proxy=$PROXY_URL agent.no_proxy=$NO_PROXY_VALUE"
  fi

  if [[ -f "$LOCAL_KERNEL_PARAMS_FILE" ]]; then
    extra="$(tr '\n' ' ' < "$LOCAL_KERNEL_PARAMS_FILE" | sed -E 's/[[:space:]]+/ /g; s/^ //; s/ $//')"
    [[ -n "$extra" ]] && params="$params $extra"
  fi

  printf '%s' "$params"
}

# Extract just the hostname from a URL like https://host:port/path.
url_host() {
  local url="$1" rest
  [[ -z "$url" ]] && return 0
  rest="${url#*://}"
  rest="${rest%%/*}"
  rest="${rest%%:*}"
  printf '%s' "$rest"
}

render_host_aliases_block() {
  if [[ "$ADD_HOST_ALIASES" != "1" ]]; then
    return 0
  fi

  local hosts=() h ip entries=""
  local api_host proxy_host
  api_host="$(url_host "$OPENAI_API_ADDRESS")"
  [[ -n "$api_host" ]] && hosts+=("$api_host")
  if [[ -n "$PROXY_URL" ]]; then
    proxy_host="$(url_host "$PROXY_URL")"
    [[ -n "$proxy_host" ]] && hosts+=("$proxy_host")
  fi

  for h in "${hosts[@]}"; do
    ip="$(getent hosts "$h" 2>/dev/null | awk '{print $1}' | head -1)"
    if [[ -n "$ip" ]]; then
      entries="${entries}    - ip: \"${ip}\"
      hostnames: [\"${h}\"]
"
    else
      log "WARNING: could not resolve '$h' from this host; not adding a hostAliases entry for it."
      log "         If the cluster has no working in-cluster DNS, name resolution for '$h' may fail inside the guest."
    fi
  done

  if [[ -n "$entries" ]]; then
    printf '  hostAliases:\n%s\n' "$entries"
  fi
}

render_proxy_env_block() {
  if [[ -z "$PROXY_URL" ]]; then
    return 0
  fi

  cat <<EOF
        - name: HTTPS_PROXY
          value: "${PROXY_URL}"
        - name: HTTP_PROXY
          value: "${PROXY_URL}"
        - name: https_proxy
          value: "${PROXY_URL}"
        - name: http_proxy
          value: "${PROXY_URL}"
        - name: NO_PROXY
          value: "${NO_PROXY_VALUE}"
        - name: no_proxy
          value: "${NO_PROXY_VALUE}"
EOF
}

render_signed_images_annotations() {
  if [[ "$SIGNED_IMAGES_ENABLED" != "1" ]]; then
    return 0
  fi

  cat <<EOF
  annotations:
    io.katacontainers.config.hypervisor.kernel_params: "agent.aa_kbc_params=cc_kbc::${SIGNED_IMAGES_KBS_URL} agent.image_policy_file=${SIGNED_IMAGES_POLICY} agent.enable_signature_verification=true"
EOF
}

chat_probe_ruby() {
  cat <<'RUBY'
require "net/http"
require "json"
require "openssl"

uri = URI(ENV.fetch("OPENAI_API_ADDRESS") + "/chat/completions")
http = Net::HTTP.new(uri.host, uri.port)
http.use_ssl = (uri.scheme == "https")
http.verify_mode = OpenSSL::SSL::VERIFY_NONE if ENV["FARADAY_SSL_VERIFY"].to_s.downcase == "none"

req = Net::HTTP::Post.new(uri)
req["Authorization"] = "Bearer #{ENV.fetch("OPENAI_API_KEY")}"
req["Content-Type"] = "application/json"
req.body = JSON.dump(
  model: ENV.fetch("NANO_BOT_MODEL"),
  messages: [
    { role: "system", content: "You are a helpful assistant running in a TDX enclave." },
    { role: "user", content: ENV.fetch("NANO_BOT_TEST_PROMPT") }
  ],
  max_tokens: 128
)

res = http.request(req)
puts "http=#{res.code}"

body = JSON.parse(res.body) rescue { "raw" => res.body }
msg = body.dig("choices", 0, "message") || {}
content = msg["content"]
content = msg["reasoning_content"] if content.nil? || content.empty?
puts(content || body["raw"] || res.body)
RUBY
}

preflight() {
  need_cmd "$CONTAINER_ENGINE"

  if ! "$CONTAINER_ENGINE" ps --format '{{.Names}}' | grep -Fxq "$CONTAINER_NAME"; then
    err "Container not running: $CONTAINER_NAME"
    exit 1
  fi

  for file in "$LOCAL_RUNTIMECLASS" "$LOCAL_CONTAINERD_SNIPPET"; do
    if [[ ! -f "$file" ]]; then
      err "Required local file not found: $file"
      exit 1
    fi
  done

  if [[ -z "$SOURCE_RUNTIME_CFG" ]]; then
    err "SOURCE_RUNTIME_CFG is required. Example: /opt/coco/config/configuration-qemu-tdx-asterinas.toml"
    exit 1
  fi
  docker_exec "test -f '$SOURCE_RUNTIME_CFG'" || {
    err "Source runtime config not found in container: $SOURCE_RUNTIME_CFG"
    exit 1
  }

  if [[ -z "$HOST_LINUX_KERNEL" ]]; then
    err "HOST_LINUX_KERNEL is required. Example: /path/to/vmlinuz-6.16.0-vsock-net-tdxguest-builtin"
    exit 1
  fi
  if [[ ! -f "$HOST_LINUX_KERNEL" ]]; then
    err "Host Linux kernel not found: $HOST_LINUX_KERNEL"
    exit 1
  fi

  if [[ -z "$LINUX_INITRD" ]]; then
    err "LINUX_INITRD is required. Example: /opt/coco/prebuilt/asterinas-coco/kata-containers-initrd.img"
    exit 1
  fi
  docker_exec "test -f '$LINUX_INITRD'" || {
    err "Kata initrd not found: $LINUX_INITRD"
    exit 1
  }
  docker_exec "test -f '$LINUX_FIRMWARE'"

  if [[ -z "$OPENAI_API_ADDRESS" ]]; then
    err "OPENAI_API_ADDRESS is required, e.g. https://api.openai.com/v1"
    exit 1
  fi

  if [[ "$SIGNED_IMAGES_ENABLED" == "1" ]]; then
    if [[ -z "$SIGNED_IMAGES_KBS_URL" || -z "$SIGNED_IMAGES_POLICY" ]]; then
      err "SIGNED_IMAGES_ENABLED=1 requires SIGNED_IMAGES_KBS_URL and SIGNED_IMAGES_POLICY."
      err "The KBS must already contain the public key and policy before deployment."
      exit 1
    fi
  fi

  log "Preflight checks passed."
}

copy_inputs_to_container() {
  log "Copying kernel, RuntimeClass, and optional containerd snippet."

  docker_exec "mkdir -p /opt/coco/manifests /etc/containerd/conf.d '$(dirname "$LINUX_KERNEL")'"
  "$CONTAINER_ENGINE" cp "$HOST_LINUX_KERNEL" "$CONTAINER_NAME:$LINUX_KERNEL"
  "$CONTAINER_ENGINE" cp "$LOCAL_RUNTIMECLASS" "$CONTAINER_NAME:$CONTAINER_RUNTIMECLASS"

  if [[ "$INSTALL_HANDLER" == "1" ]]; then
    "$CONTAINER_ENGINE" cp "$LOCAL_CONTAINERD_SNIPPET" "$CONTAINER_NAME:$CONTAINER_CONTAINERD_SNIPPET"
    docker_exec "ls -l '$CONTAINER_CONTAINERD_SNIPPET'"
  fi
}

prepare_linux_runtime_cfg() {
  log "Preparing Linux runtime configuration."

  local sha_src sha_live
  sha_src="$(docker_exec "sha256sum < '$SOURCE_RUNTIME_CFG'" 2>/dev/null | awk '{print $1}')"
  sha_live="$(docker_exec "sha256sum < '$LINUX_RUNTIME_CFG'" 2>/dev/null | awk '{print $1}')" || sha_live=""

  if [[ "$FORCE_RECREATE_LINUX_CFG" == "1" ]] || [[ "$sha_src" != "$sha_live" ]]; then
    log "Creating Linux runtime config from a full copy of $SOURCE_RUNTIME_CFG"
    # IMPORTANT: do NOT write a minimal/hand-rolled TOML here. The Kata
    # runtime config has many required fields (internetworking_model,
    # sandbox_cgroup_only, use_qemu_user_net, etc.) that a short custom
    # TOML would omit, which causes every sandbox creation to silently fail.
    # Instead, copy the full base config and only patch the kernel image +
    # kernel_params fields.
    local kparams
    kparams="$(kernel_params)"
    docker_exec "mkdir -p '$(dirname '$LINUX_RUNTIME_CFG')'"
    docker_exec "cp -a '$SOURCE_RUNTIME_CFG' '$LINUX_RUNTIME_CFG'"
    docker_exec "sed -i 's#^kernel = .*#kernel = \"$LINUX_KERNEL\"#' '$LINUX_RUNTIME_CFG'"
    docker_exec "sed -i 's#^kernel_params = .*#kernel_params = \"$kparams\"#' '$LINUX_RUNTIME_CFG'"
    docker_exec "diff '$SOURCE_RUNTIME_CFG' '$LINUX_RUNTIME_CFG' || true"
  else
    log "Linux runtime config unchanged, skipping recreation."
  fi
}

ensure_devlog_socket() {
  # The kata shim fails ALL new sandbox creation with "Unix syslog delivery
  # error" if /dev/log is missing inside the CoCo dev container (e.g. its
  # socat forwarder died on a previous restart). Recreate it if needed.
  docker_exec "
    if [ ! -S /dev/log ] || ! kill -0 \$(cat /tmp/socat-devlog.pid 2>/dev/null) 2>/dev/null; then
      command -v socat >/dev/null 2>&1 || { echo 'socat not found, cannot recreate /dev/log' >&2; exit 0; }
      rm -f /dev/log
      nohup socat -u UNIX-RECVFROM:/dev/log,fork OPEN:/tmp/kata-syslog-linux.log,creat,append >/tmp/socat-devlog.out 2>/tmp/socat-devlog.err &
      disown
      sleep 1
      echo \$! > /tmp/socat-devlog.pid
    fi
    ls -la /dev/log 2>&1 || true
  "
}

ensure_containerd_tmpmounts() {
  docker_exec "
    mkdir -p /var/lib/containerd/tmpmounts
    if ! mountpoint -q /var/lib/containerd/tmpmounts; then
      mount -t tmpfs -o size=512m tmpfs /var/lib/containerd/tmpmounts
    fi
    findmnt /var/lib/containerd/tmpmounts
  "
}

restart_nydus_snapshotter() {
  docker_exec "
    nydus_cmd='/opt/coco/nydus-snapshotter/containerd-nydus-grpc'

    if pgrep -f \"\$nydus_cmd\" >/dev/null 2>&1; then
      pkill -f \"\$nydus_cmd\" || true
      sleep 2
    fi

    export NO_PROXY='$NO_PROXY_VALUE'
    export no_proxy='$NO_PROXY_VALUE'

    if [[ -n '$PROXY_URL' ]]; then
      export HTTP_PROXY='$PROXY_URL'
      export HTTPS_PROXY='$PROXY_URL'
      export http_proxy='$PROXY_URL'
      export https_proxy='$PROXY_URL'
    else
      unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    fi

    nohup /opt/coco/nydus-snapshotter/containerd-nydus-grpc \
      --config /etc/nydus/config-proxy.toml \
      --log-to-stdout \
      >/tmp/containerd-nydus-grpc.out 2>/tmp/containerd-nydus-grpc.err &
    disown
    sleep 1

    pgrep -af \"\$nydus_cmd\" || true
    pid=\$(pgrep -nf \"\$nydus_cmd\" || true)
    if [[ -n \"\$pid\" ]]; then
      tr '\\0' '\\n' < /proc/\$pid/environ | grep -i 'proxy' || true
    fi
  "
}

restart_containerd_if_requested() {
  if [[ "$RESTART_CONTAINERD" != "1" ]]; then
    log "Skipping containerd restart (disabled by configuration)."
    return 0
  fi

  log "Checking containerd configuration."

  if docker_exec "test -f '$CONTAINER_CONTAINERD_SNIPPET'"; then
    docker_exec "test -d /etc/containerd/conf.d" && \
      "$CONTAINER_ENGINE" exec "$CONTAINER_NAME" bash -lc "rm -f /etc/containerd/conf.d/*.toml.bak 2>/dev/null; ls -la /etc/containerd/conf.d/"
    docker_exec "test -s '$CONTAINER_CONTAINERD_SNIPPET' && echo 'Snippet exists and has content'"
  fi

  ensure_devlog_socket
  ensure_containerd_tmpmounts

  log "Restarting containerd with updated proxy bypasses."
  docker_exec "
    if pidof containerd >/dev/null 2>&1; then
      pkill -x containerd || true
      sleep 2
    fi

    export NO_PROXY='$NO_PROXY_VALUE'
    export no_proxy='$NO_PROXY_VALUE'

    if [[ -n '$PROXY_URL' ]]; then
      export HTTP_PROXY='$PROXY_URL'
      export HTTPS_PROXY='$PROXY_URL'
      export http_proxy='$PROXY_URL'
      export https_proxy='$PROXY_URL'
    else
      unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy
    fi

    nohup containerd >/tmp/containerd.out 2>/tmp/containerd.err &
    disown
    sleep 3

    pid=\$(pidof containerd | awk '{print \$1}')
    if [[ -n \"\$pid\" ]]; then
      tr '\\0' '\\n' < /proc/\$pid/environ | grep -i 'proxy' || true
    fi
  "
  log "Restarting containerd-nydus-grpc with updated proxy bypasses."
  restart_nydus_snapshotter
  ensure_containerd_tmpmounts
  docker_exec "ps aux | grep containerd"
}

apply_runtimeclass() {
  if [[ "$APPLY_RUNTIMECLASS" != "1" ]]; then
    log "Skipping RuntimeClass application (disabled by configuration)."
    return 0
  fi

  log "Applying RuntimeClass for kata-qemu-tdx-linux."

  docker_exec "test -f '$CONTAINER_RUNTIMECLASS'" || {
    err "RuntimeClass manifest not found in container at $CONTAINER_RUNTIMECLASS"
    return 1
  }

  docker_exec "kubectl apply -f '$CONTAINER_RUNTIMECLASS'" 2>/dev/null || {
    docker_exec "kubectl apply --server-side -f '$CONTAINER_RUNTIMECLASS'" 2>/dev/null || true
  }

  log "RuntimeClass applied."
}

ensure_api_key_secret() {
  local exists
  exists="$(docker_exec "kubectl get secret '$API_KEY_SECRET_NAME' -o name" 2>/dev/null || true)"
  if [[ -n "$exists" ]]; then
    log "Secret '$API_KEY_SECRET_NAME' already exists, leaving it untouched."
    return 0
  fi

  if [[ -z "$OPENAI_API_KEY" ]]; then
    err "Kubernetes secret '$API_KEY_SECRET_NAME' does not exist and OPENAI_API_KEY is not set."
    err "Either export OPENAI_API_KEY=<your-key> before running this script, or create the"
    err "secret yourself: $CONTAINER_ENGINE exec $CONTAINER_NAME kubectl create secret generic $API_KEY_SECRET_NAME --from-literal=$API_KEY_SECRET_KEY=<your-key>"
    exit 1
  fi

  log "Creating Kubernetes secret '$API_KEY_SECRET_NAME' from OPENAI_API_KEY."
  docker_exec "kubectl create secret generic '$API_KEY_SECRET_NAME' --from-literal='$API_KEY_SECRET_KEY=$OPENAI_API_KEY'"
}

prepare_nano_bot_image() {
  if [[ -n "$NANO_BOT_IMAGE" ]]; then
    log "Using explicitly provided NANO_BOT_IMAGE=$NANO_BOT_IMAGE (skipping local build/registry)."
    return 0
  fi

  if [[ "$USE_LOCAL_REGISTRY" != "1" ]]; then
    err "NANO_BOT_IMAGE is not set and USE_LOCAL_REGISTRY=0. Nothing to deploy."
    err "Either set NANO_BOT_IMAGE to a pullable image reference, or leave USE_LOCAL_REGISTRY=1."
    exit 1
  fi

  log "Building/publishing the nano_bot image via a local registry."
  local registry_address
  registry_address="$(CONTAINER_ENGINE="$CONTAINER_ENGINE" CONTAINER_NAME="$CONTAINER_NAME" LOCAL_REGISTRY_NAME="$LOCAL_REGISTRY_NAME" LOCAL_REGISTRY_PORT="$LOCAL_REGISTRY_PORT" "$SCRIPT_DIR/setup_local_registry.sh")"

  NANO_BOT_IMAGE="$(CONTAINER_ENGINE="$CONTAINER_ENGINE" REGISTRY_ADDRESS="$registry_address" IMAGE_NAME="$IMAGE_NAME" IMAGE_TAG="$IMAGE_TAG" FLATTEN_IMAGE="$FLATTEN_IMAGE" FORCE_REBUILD="$FORCE_REBUILD_IMAGE" "$SCRIPT_DIR/build_and_push_nano_bot_image.sh")"

  CONTAINER_ENGINE="$CONTAINER_ENGINE" CONTAINER_NAME="$CONTAINER_NAME" REGISTRY_ADDRESS="$registry_address" LINUX_INITRD="$LINUX_INITRD" "$SCRIPT_DIR/configure_guest_registry_mirror.sh"
}

detect_workload_node() {
  if [[ -n "$WORKLOAD_NODE_NAME" ]]; then
    printf '%s' "$WORKLOAD_NODE_NAME"
    return 0
  fi

  local node_count single_node
  node_count="$(docker_exec "kubectl get nodes --no-headers 2>/dev/null | wc -l" | tr -d '[:space:]')"
  if [[ "$node_count" == "1" ]]; then
    single_node="$(docker_exec "kubectl get nodes --no-headers -o custom-columns=NAME:.metadata.name 2>/dev/null" | tr -d '[:space:]')"
    printf '%s' "$single_node"
  fi
}

current_workload_image() {
  docker_exec "kubectl get pod '$POD_NAME' -o jsonpath='{.spec.containers[0].image}'" 2>/dev/null || true
}

resolve_probe_image() {
  local live_image

  if [[ -n "$PROBE_IMAGE" ]]; then
    printf '%s' "$PROBE_IMAGE"
    return 0
  fi

  live_image="$(current_workload_image)"
  if [[ -n "$live_image" ]]; then
    printf '%s' "$live_image"
    return 0
  fi

  printf '%s' "$NANO_BOT_IMAGE"
}

# Renders the nano_bot Pod manifest to a temp file using only environment
# variables (no committed secrets/hostnames). Prints the rendered file path.
render_nano_bot_manifest() {
  local rendered="/tmp/${POD_NAME}.rendered.yaml"
  local workload_node_name node_name_block=""
  local host_aliases_block proxy_env_block signed_images_annotations

  workload_node_name="$(detect_workload_node)"
  if [[ -n "$workload_node_name" ]]; then
    node_name_block="  nodeName: ${workload_node_name}
"
  fi

  host_aliases_block="$(render_host_aliases_block)"
  proxy_env_block="$(render_proxy_env_block)"
  signed_images_annotations="$(render_signed_images_annotations)"

  cat > "$rendered" << YAMLEOF
apiVersion: v1
kind: Pod
metadata:
  name: ${POD_NAME}
${signed_images_annotations}
spec:
  runtimeClassName: kata-qemu-tdx-linux
${node_name_block}${host_aliases_block}
  containers:
    - name: nano-bot
      image: "${NANO_BOT_IMAGE}"
      imagePullPolicy: ${IMAGE_PULL_POLICY}
      command:
        - /bin/bash
        - -lc
        - |
          mkdir -p /root/.config/nano-bots /root/.local/share/nano-bots/cartridges /root/.local/state/nano-bots
          exec sleep infinity
      env:
        - name: GEM_HOME
          value: "/usr/local/bundle"
        - name: BUNDLE_APP_CONFIG
          value: "/usr/local/bundle"
        - name: PATH
          value: "/usr/local/bundle/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        - name: TMPDIR
          value: "/tmp"
        - name: TMP
          value: "/tmp"
        - name: TEMP
          value: "/tmp"
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: "${API_KEY_SECRET_NAME}"
              key: "${API_KEY_SECRET_KEY}"
        - name: OPENAI_API_ADDRESS
          value: "${OPENAI_API_ADDRESS}"
        - name: NANO_BOT_MODEL
          value: "${NANO_BOT_MODEL}"
        - name: NANO_BOTS_END_USER
          value: "default"
        - name: FARADAY_SSL_VERIFY
          value: "${FARADAY_SSL_VERIFY}"
${proxy_env_block}
      volumeMounts:
        - name: confidential-workdir
          mountPath: /tmp
        - name: confidential-workdir
          mountPath: /var/tmp
        - name: confidential-workdir
          mountPath: /root/.config
        - name: confidential-workdir
          mountPath: /root/.local
  volumes:
    - name: confidential-workdir
      emptyDir:
        sizeLimit: 1Gi
YAMLEOF

  echo "$rendered"
}

render_nano_bot_probe_manifest() {
  local probe_image="$1"
  local probe_pod="$PROBE_POD_NAME"
  local rendered="/tmp/${probe_pod}.rendered.yaml"
  local workload_node_name node_name_block=""
  local host_aliases_block proxy_env_block signed_images_annotations

  workload_node_name="$(detect_workload_node)"
  if [[ -n "$workload_node_name" ]]; then
    node_name_block="  nodeName: ${workload_node_name}
"
  fi

  host_aliases_block="$(render_host_aliases_block)"
  proxy_env_block="$(render_proxy_env_block)"
  signed_images_annotations="$(render_signed_images_annotations)"

  cat > "$rendered" <<YAMLEOF
apiVersion: v1
kind: Pod
metadata:
  name: ${probe_pod}
${signed_images_annotations}
spec:
  restartPolicy: Never
  runtimeClassName: kata-qemu-tdx-linux
${node_name_block}${host_aliases_block}
  containers:
    - name: nano-bot
      image: "${probe_image}"
      imagePullPolicy: ${PROBE_IMAGE_PULL_POLICY}
      command:
        - /bin/bash
        - -lc
        - |
          mkdir -p /root/.config/nano-bots /root/.local/share/nano-bots/cartridges /root/.local/state/nano-bots
          echo "nano-bot chat probe starting"
          echo "model=${NANO_BOT_MODEL}"
          ruby -e '
        $(chat_probe_ruby | sed 's/^/          /')
          '
      env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: "${API_KEY_SECRET_NAME}"
              key: "${API_KEY_SECRET_KEY}"
        - name: OPENAI_API_ADDRESS
          value: "${OPENAI_API_ADDRESS}"
        - name: NANO_BOT_MODEL
          value: "${NANO_BOT_MODEL}"
        - name: NANO_BOT_TEST_PROMPT
          value: "${NANO_BOT_TEST_PROMPT}"
        - name: TMPDIR
          value: "/tmp"
        - name: TMP
          value: "/tmp"
        - name: TEMP
          value: "/tmp"
        - name: FARADAY_SSL_VERIFY
          value: "${FARADAY_SSL_VERIFY}"
${proxy_env_block}
      volumeMounts:
        - name: confidential-workdir
          mountPath: /tmp
        - name: confidential-workdir
          mountPath: /var/tmp
        - name: confidential-workdir
          mountPath: /root/.config
        - name: confidential-workdir
          mountPath: /root/.local
  volumes:
    - name: confidential-workdir
      emptyDir:
        sizeLimit: 1Gi
YAMLEOF

  echo "$rendered"
}

show_pod_local_log() {
  local pod_name="$1"
  local container_name="${2:-nano-bot}"
  local pod_uid log_path

  pod_uid="$(docker_exec "kubectl get pod '$pod_name' -o jsonpath='{.metadata.uid}'" 2>/dev/null || true)"
  if [[ -z "$pod_uid" ]]; then
    err "Could not determine UID for pod $pod_name"
    return 1
  fi

  log_path="/var/log/pods/default_${pod_name}_${pod_uid}/${container_name}/0.log"
  docker_exec "test -f '$log_path' && cat '$log_path'" || {
    err "Local pod log not found: $log_path"
    return 1
  }
}

run_nano_bot_probe() {
  local probe_pod="$PROBE_POD_NAME"
  local probe_image rendered
  local probe_log

  probe_image="$(resolve_probe_image)"
  if [[ -z "$probe_image" ]]; then
    err "Could not determine a probe image. Set PROBE_IMAGE explicitly or deploy the workload first."
    return 1
  fi

  if [[ -n "$NANO_BOT_IMAGE" && "$probe_image" != "$NANO_BOT_IMAGE" ]]; then
    log "Probe will reuse running workload image $probe_image instead of the newly resolved image $NANO_BOT_IMAGE."
  else
    log "Probe will use image $probe_image with imagePullPolicy=$PROBE_IMAGE_PULL_POLICY."
  fi

  rendered="$(render_nano_bot_probe_manifest "$probe_image")"
  "$CONTAINER_ENGINE" cp "$rendered" "$CONTAINER_NAME:$CONTAINER_MANIFEST.probe"
  recreate_pod_from_manifest "$probe_pod" "$CONTAINER_MANIFEST.probe" 1
  docker_exec "kubectl wait --for=jsonpath='{.status.phase}'=Succeeded pod/'$probe_pod' --timeout=$WAIT_TIMEOUT" 2>/dev/null || {
    err "Probe pod $probe_pod did not complete successfully within $WAIT_TIMEOUT"
    docker_exec "kubectl describe pod '$probe_pod'"
    show_pod_local_log "$probe_pod" || true
    return 1
  }

  probe_log="$(show_pod_local_log "$probe_pod")" || return 1
  echo "--- Probe Pod Log (node-local fallback) ---"
  printf '%s\n' "$probe_log"

  if grep -q 'Error:' <<<"$probe_log"; then
    err "Probe pod completed but the guest-side chat request still returned an application error."
    return 1
  fi
  if ! grep -q 'http=200' <<<"$probe_log"; then
    err "Probe pod completed, but the guest-side chat request did not return HTTP 200."
    return 1
  fi
}

run_workload() {
  if [[ "$RUN_WORKLOAD" != "1" ]]; then
    log "Skipping workload execution (disabled by configuration)."
    return 0
  fi

  ensure_api_key_secret
  prepare_nano_bot_image

  log "Rendering nano_bot Pod manifest."
  local rendered
  rendered="$(render_nano_bot_manifest)"
  log "Rendered manifest: $rendered"

  log "Deploying CoCo TDX workload."
  "$CONTAINER_ENGINE" cp "$rendered" "$CONTAINER_NAME:$CONTAINER_MANIFEST"
  recreate_pod_from_manifest "$POD_NAME" "$CONTAINER_MANIFEST" 1

  log "Waiting for pod $POD_NAME to start (timeout: $WAIT_TIMEOUT)"
  docker_exec "kubectl wait --for=condition=Ready pod/$POD_NAME --timeout=$WAIT_TIMEOUT" 2>/dev/null || {
    err "Pod $POD_NAME did not become ready within $WAIT_TIMEOUT"
    docker_exec "kubectl describe pod $POD_NAME"
    docker_exec "kubectl logs $POD_NAME --all-containers"
    exit 1
  }

  log "Workload deployed successfully."

  if [[ "$IMAGE_METADATA_VALIDATION" == "1" ]]; then
    log "Validating deployed image metadata."
    IMAGE_REFERENCE="$NANO_BOT_IMAGE" \
    IMAGE_INSPECT_REFERENCE="$IMAGE_METADATA_INSPECT_REFERENCE" \
    EXPECTED_MANIFEST_DIGEST="$IMAGE_METADATA_EXPECTED_DIGEST" \
    IMAGE_METADATA_COSIGN_KEY="$IMAGE_METADATA_COSIGN_KEY" \
    REPORT_FILE="$IMAGE_METADATA_REPORT" \
    CONTAINER_ENGINE="$CONTAINER_ENGINE" \
    CONTAINER_NAME="$CONTAINER_NAME" \
    POD_NAME="$POD_NAME" \
    SIGNED_IMAGES_ENABLED="$SIGNED_IMAGES_ENABLED" \
    SIGNED_IMAGES_KBS_URL="$SIGNED_IMAGES_KBS_URL" \
    SIGNED_IMAGES_POLICY="$SIGNED_IMAGES_POLICY" \
      "$SCRIPT_DIR/validate_image_metadata.sh"
  fi
}

capture_vm_tee_logs() {
  log "Capturing VM TEE startup logs (Step 1)..."

  echo ""
  echo "=========================================="
  echo "VM TEE Startup Capture (Step 1)"
  echo "=========================================="
  echo ""

  echo "--- TDX Guest Detection ---"
  docker_exec "dmesg | grep -i 'tdx\|trust.domain\|TDX' | head -10" || echo "TDX messages not found in dmesg"
  echo ""

  echo "--- Kernel Command Line ---"
  docker_exec "cat /proc/cmdline" || echo "Failed to read kernel command line"
  echo ""

  echo "--- Kata Agent Logs ---"
  docker_exec "cat /var/log/kata*/syslog 2>/dev/null | tail -30" || echo "Kata syslog not accessible"
  echo ""

  echo "=========================================="
  echo "VM TEE Startup Capture Complete"
  echo "=========================================="
  echo ""
}

verify_workload_startup() {
  log "Verifying workload startup (Step 7)..."

  echo ""
  echo "=========================================="
  echo "Workload Startup Verification (Step 7)"
  echo "=========================================="
  echo ""

  echo "--- Pod Status ---"
  docker_exec "kubectl get pod $POD_NAME -o wide" || true
  echo ""

  echo "--- Guest OS Release ---"
  docker_exec "kubectl exec $POD_NAME -- cat /etc/os-release" 2>/dev/null || echo "Failed to read /etc/os-release"
  echo ""

  echo "--- Container Process List ---"
  docker_exec "kubectl exec $POD_NAME -- ps aux" 2>/dev/null | head -10 || echo "Failed to get process list"
  echo ""

  echo "=========================================="
  echo "Workload Startup Verification Complete"
  echo "=========================================="
  echo ""
}

run_nano_bot() {
  if [[ "$RUN_NANO_BOT_TEST" != "1" ]]; then
    log "Skipping nano_bot chat test (disabled by configuration)."
    return 0
  fi

  log "Running nano_bot workload inside the TDX guest VM (Step 7 Extended)..."

  echo ""
  echo "=========================================="
  echo "nano_bot Workload (Step 7 Extended)"
  echo "=========================================="
  echo ""

  echo "--- Testing Chat Bot via one-shot guest probe pod: ${PROBE_POD_NAME} ---"
  run_nano_bot_probe

  echo ""
  echo "=========================================="
  echo "nano_bot Workload Complete"
  echo "=========================================="
  echo ""
  echo "SUCCESS: Chat bot is running inside the TDX guest VM (pod: $POD_NAME)!"
  echo "         Model: $NANO_BOT_MODEL"
  echo ""
}

main() {
  log "Starting CoCo + TDX + nano_bot flow."
  preflight
  copy_inputs_to_container
  prepare_linux_runtime_cfg
  restart_containerd_if_requested
  apply_runtimeclass
  run_workload
  capture_vm_tee_logs
  verify_workload_startup
  run_nano_bot
  log "Done. CoCo + TDX + nano_bot flow completed."
}

main "$@"

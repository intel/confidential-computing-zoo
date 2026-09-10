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

# Deploy OpenClaw in the Linux TDX Kata runtime without host Docker access.

set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "INFO: $*"; }

usage() {
  cat <<'EOF'
Usage: run-coco-tdx.sh [options]

Credentials are read from Kubernetes Secrets and are never accepted as
command-line values or printed by this script.

Options:
  --image IMAGE            Image (default: docker.io/library/openclaw-coco-tdx:latest)
  --pod NAME               Pod name (default: openclaw-coco-tdx-gateway)
  --namespace NAME         Namespace (default: default)
  --runtime-class CLASS    RuntimeClass (default: kata-qemu-tdx-linux)
  --api-secret NAME        Secret containing API key (default: agent-api-key)
  --api-secret-key KEY     Key inside api-secret (default: OPENAI_API_KEY)
  --gateway-secret NAME    Secret containing OPENCLAW_GATEWAY_TOKEN (default: openclaw-gateway-token)
  --model MODEL            Model name (default: openrouter/nvidia/nemotron-3.5-lightning:free)
  --max-tokens NUM         Max tokens (default: 4096)
  --proxy URL              HTTP(S) proxy reachable from the guest
  --node-name NAME         Optional nodeName
  --signed-images          Require guest-side image signature verification
  --kbs-url URL            Trustee KBS URL reachable from the guest
  --image-policy URI       Image policy URI, for example kbs:///default/security-policy/openclaw
  --delete                 Delete the existing Pod before deploying
  --help                   Show this help

Create the gateway token without putting it in shell history:
  read -r -s TOKEN; kubectl create secret generic openclaw-gateway-token \
    --from-literal=OPENCLAW_GATEWAY_TOKEN="$TOKEN"
EOF
}

IMAGE="${OPENCLAW_IMAGE:-docker.io/library/openclaw-coco-tdx:latest}"
POD_NAME="${OPENCLAW_POD_NAME:-openclaw-coco-tdx-gateway}"
NAMESPACE="${OPENCLAW_NAMESPACE:-default}"
RUNTIME_CLASS="${OPENCLAW_RUNTIME_CLASS:-kata-qemu-tdx-linux}"
API_SECRET="${OPENCLAW_API_SECRET:-agent-api-key}"
API_SECRET_KEY="${OPENCLAW_API_SECRET_KEY:-OPENAI_API_KEY}"
GATEWAY_SECRET="${OPENCLAW_GATEWAY_SECRET:-openclaw-gateway-token}"
MODEL="${OPENCLAW_MODEL:-openrouter/nvidia/nemotron-3.5-lightning:free}"
MAX_TOKENS="${OPENCLAW_MAX_TOKENS:-4096}"
PROXY_URL="${OPENCLAW_PROXY_URL:-${HTTPS_PROXY:-${https_proxy:-}}}"
NO_PROXY_VALUE="${OPENCLAW_NO_PROXY:-127.0.0.1,localhost,10.244.0.0/16,10.96.0.0/12}"
NODE_NAME="${OPENCLAW_NODE_NAME:-}"
SIGNED_IMAGES="${OPENCLAW_SIGNED_IMAGES:-0}"
KBS_URL="${OPENCLAW_KBS_URL:-}"
IMAGE_POLICY="${OPENCLAW_IMAGE_POLICY:-}"
DELETE_EXISTING=0
KUBECTL="${KUBECTL:-kubectl}"

while (($#)); do
  case "$1" in
    --image) [[ $# -ge 2 ]] || fail "--image requires a value"; IMAGE="$2"; shift 2 ;;
    --pod) [[ $# -ge 2 ]] || fail "--pod requires a value"; POD_NAME="$2"; shift 2 ;;
    --namespace) [[ $# -ge 2 ]] || fail "--namespace requires a value"; NAMESPACE="$2"; shift 2 ;;
    --runtime-class) [[ $# -ge 2 ]] || fail "--runtime-class requires a value"; RUNTIME_CLASS="$2"; shift 2 ;;
    --api-secret) [[ $# -ge 2 ]] || fail "--api-secret requires a value"; API_SECRET="$2"; shift 2 ;;
    --api-secret-key) [[ $# -ge 2 ]] || fail "--api-secret-key requires a value"; API_SECRET_KEY="$2"; shift 2 ;;
    --gateway-secret) [[ $# -ge 2 ]] || fail "--gateway-secret requires a value"; GATEWAY_SECRET="$2"; shift 2 ;;
    --model) [[ $# -ge 2 ]] || fail "--model requires a value"; MODEL="$2"; shift 2 ;;
    --max-tokens) [[ $# -ge 2 ]] || fail "--max-tokens requires a value"; MAX_TOKENS="$2"; shift 2 ;;
    --proxy) [[ $# -ge 2 ]] || fail "--proxy requires a value"; PROXY_URL="$2"; shift 2 ;;
    --node-name) [[ $# -ge 2 ]] || fail "--node-name requires a value"; NODE_NAME="$2"; shift 2 ;;
    --signed-images) SIGNED_IMAGES=1; shift ;;
    --kbs-url) [[ $# -ge 2 ]] || fail "--kbs-url requires a value"; KBS_URL="$2"; shift 2 ;;
    --image-policy) [[ $# -ge 2 ]] || fail "--image-policy requires a value"; IMAGE_POLICY="$2"; shift 2 ;;
    --delete) DELETE_EXISTING=1; shift ;;
    --help|-h) usage; exit 0 ;;
    *) fail "unknown option: $1" ;;
  esac
done

command -v "$KUBECTL" >/dev/null 2>&1 || fail "kubectl is not available"
for value_name in IMAGE POD_NAME NAMESPACE RUNTIME_CLASS API_SECRET API_SECRET_KEY GATEWAY_SECRET MODEL MAX_TOKENS PROXY_URL NO_PROXY_VALUE NODE_NAME KBS_URL IMAGE_POLICY; do
  value="${!value_name}"
  [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] || fail "$value_name contains a newline"
done
[[ "$POD_NAME" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || fail "invalid Pod name: $POD_NAME"
[[ "$NAMESPACE" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ ]] || fail "invalid namespace: $NAMESPACE"
[[ "$IMAGE" == */*:* ]] || fail "image must include repository and tag: $IMAGE"
[[ "$MODEL" =~ ^[A-Za-z0-9._:/-]+$ ]] || fail "model contains unsupported characters: $MODEL"
[[ "$MAX_TOKENS" =~ ^[1-9][0-9]*$ ]] || fail "max-tokens must be a positive integer"
if [[ "$SIGNED_IMAGES" == "1" ]]; then
  [[ "$KBS_URL" =~ ^https?://[^[:space:]]+$ ]] || fail "signed image verification requires a valid --kbs-url"
  [[ "$IMAGE_POLICY" =~ ^kbs:///[^[:space:]]+$ ]] || fail "signed image verification requires a valid --image-policy"
fi

yaml_string() {
  local value="$1"
  value="${value//\'/\'\'}"
  printf "'%s'" "$value"
}

manifest="$(mktemp)"
trap 'rm -f "$manifest"' EXIT
if [[ "$SIGNED_IMAGES" == "1" ]]; then
  signed_images_annotations="  annotations:
    io.katacontainers.config.hypervisor.kernel_params: $(yaml_string "agent.aa_kbc_params=cc_kbc::$KBS_URL agent.image_policy_file=$IMAGE_POLICY agent.enable_signature_verification=true")"
else
  signed_images_annotations=""
fi
cat >"$manifest" <<YAML
apiVersion: v1
kind: Pod
metadata:
  name: $(yaml_string "$POD_NAME")
  namespace: $(yaml_string "$NAMESPACE")
  labels:
    app: openclaw-coco-tdx
$signed_images_annotations
spec:
  runtimeClassName: $(yaml_string "$RUNTIME_CLASS")
$([ -n "$NODE_NAME" ] && printf '  nodeName: %s\n' "$(yaml_string "$NODE_NAME")")
  automountServiceAccountToken: false
  restartPolicy: Always
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containers:
    - name: openclaw
      image: $(yaml_string "$IMAGE")
      imagePullPolicy: IfNotPresent
      securityContext:
        allowPrivilegeEscalation: false
        capabilities:
          drop: [ALL]
      env:
        - name: HOME
          value: /dev/shm/openclaw-state
        - name: OPENCLAW_STATE_DIR
          value: /dev/shm/openclaw-state
        - name: OPENCLAW_CONFIG_PATH
          value: /dev/shm/openclaw-state/openclaw.json
        - name: XDG_CACHE_HOME
          value: /dev/shm/openclaw-cache
        - name: OPENROUTER_API_KEY
          valueFrom:
            secretKeyRef:
              name: $(yaml_string "$API_SECRET")
              key: $(yaml_string "$API_SECRET_KEY")
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: $(yaml_string "$API_SECRET")
              key: $(yaml_string "$API_SECRET_KEY")
        - name: OPENCLAW_GATEWAY_TOKEN
          valueFrom:
            secretKeyRef:
              name: $(yaml_string "$GATEWAY_SECRET")
              key: OPENCLAW_GATEWAY_TOKEN
        - name: HTTP_PROXY
          value: $(yaml_string "$PROXY_URL")
        - name: HTTPS_PROXY
          value: $(yaml_string "$PROXY_URL")
        - name: http_proxy
          value: $(yaml_string "$PROXY_URL")
        - name: https_proxy
          value: $(yaml_string "$PROXY_URL")
        - name: NO_PROXY
          value: $(yaml_string "$NO_PROXY_VALUE")
        - name: no_proxy
          value: $(yaml_string "$NO_PROXY_VALUE")
      command: ["sh", "-eu", "-c"]
      args:
        - >-
          mkdir -p /dev/shm/openclaw-state /dev/shm/openclaw-cache;
          node /app/dist/index.js config set gateway.mode local;
          node /app/dist/index.js config set gateway.bind loopback;
          node /app/dist/index.js config set gateway.auth.mode token;
          node /app/dist/index.js config set agents.defaults.sandbox.mode off;
          node /app/dist/index.js config set plugins.entries.perplexity.enabled false --strict-json;
          node /app/dist/index.js config set agents.defaults.model "$MODEL";
          node /app/dist/index.js config set "agents.defaults.models[\\\"$MODEL\\\"].params.maxTokens" "$MAX_TOKENS" --strict-json;
          exec node /app/dist/index.js gateway run --bind loopback --auth token --port 18789
      volumeMounts:
        - name: dshm
          mountPath: /dev/shm
      readinessProbe:
        exec:
          command:
            - node
            - -e
            - >-
              const token = process.env.OPENCLAW_GATEWAY_TOKEN || '';
              const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
              fetch('http://127.0.0.1:18789/health', { headers })
                .then(r => process.exit(r.ok ? 0 : 1))
                .catch(() => {
                  fetch('http://127.0.0.1:18789/healthz', { headers })
                    .then(r => process.exit(r.ok ? 0 : 1))
                    .catch(() => process.exit(1));
                });
        periodSeconds: 10
        timeoutSeconds: 3
        failureThreshold: 12
  volumes:
    - name: dshm
      emptyDir:
        medium: Memory
        sizeLimit: 4Gi
YAML

"$KUBECTL" get runtimeclass "$RUNTIME_CLASS" >/dev/null || fail "RuntimeClass $RUNTIME_CLASS is unavailable"
"$KUBECTL" get secret "$API_SECRET" -n "$NAMESPACE" >/dev/null || fail "API Secret is unavailable"
"$KUBECTL" get secret "$GATEWAY_SECRET" -n "$NAMESPACE" >/dev/null || fail "Gateway Secret is unavailable"
[[ "$DELETE_EXISTING" -eq 1 ]] && "$KUBECTL" delete pod "$POD_NAME" -n "$NAMESPACE" --ignore-not-found --wait=true >/dev/null
"$KUBECTL" apply -f "$manifest"
if ! "$KUBECTL" wait --for=condition=Ready "pod/$POD_NAME" -n "$NAMESPACE" --timeout=10m; then
  echo "ERROR: Pod did not become Ready; collecting diagnostics" >&2
  "$KUBECTL" get pod "$POD_NAME" -n "$NAMESPACE" -o wide >&2 || true
  "$KUBECTL" describe pod "$POD_NAME" -n "$NAMESPACE" >&2 || true
  "$KUBECTL" get events -n "$NAMESPACE" --field-selector "involvedObject.name=$POD_NAME" --sort-by=.lastTimestamp >&2 || true
  "$KUBECTL" logs "$POD_NAME" -n "$NAMESPACE" --all-containers=true --tail=200 >&2 || true
  exit 1
fi

info "Pod is ready: $POD_NAME (runtimeClass=$RUNTIME_CLASS)"
info "Credentials were injected from Secrets and were not printed."
info "Chat with:"
info "  $KUBECTL exec -n $NAMESPACE -it $POD_NAME -- sh -lc 'node /app/dist/index.js agent --message \"你好，请检查 TDX 状态\" --json'"
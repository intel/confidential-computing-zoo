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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
TC_API_URL="${TC_API_URL:-http://127.0.0.1:8000}"

OPENCLAW_WORKLOAD_ID="${OPENCLAW_WORKLOAD_ID:-openclaw-agent}"
OPENCLAW_IMAGE_ID="${OPENCLAW_IMAGE_ID:-openclaw-sbx}"
OPENCLAW_IMAGE_NAME="${OPENCLAW_IMAGE_NAME:-localhost:5000/openclaw-sbx:latest}"
OPENCLAW_IMAGE_URL="${OPENCLAW_IMAGE_URL:-docker://registry:5000/openclaw-sbx:latest}"
OPENCLAW_DOCKERFILE="${OPENCLAW_DOCKERFILE:-$SCRIPT_DIR/Dockerfile.sbx}"
OPENCLAW_BUILD_CONTEXT="${OPENCLAW_BUILD_CONTEXT:-$SCRIPT_DIR}"
OPENCLAW_USER_ID="${OPENCLAW_USER_ID:-openclaw-demo}"
OPENCLAW_ATTESTATION_REQUIRED="${OPENCLAW_ATTESTATION_REQUIRED:-false}"
OPENCLAW_DOCKERCMD="${OPENCLAW_DOCKERCMD:-}"
OPENCLAW_BUILD_IMAGE="${OPENCLAW_BUILD_IMAGE:-1}"
OPENCLAW_PUSH_IMAGE="${OPENCLAW_PUSH_IMAGE:-1}"
OPENCLAW_BUILDKIT="${OPENCLAW_BUILDKIT:-1}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-40}"

log() {
    printf '[step2] %s\n' "$*"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

resolve_tc_client_cmd() {
    if command -v tc-oidc-verification-code >/dev/null 2>&1; then
        TC_CLIENT_CMD=("$(command -v tc-oidc-verification-code)")
        return 0
    fi

    if [[ -x "$REPO_ROOT/core/tc_api/venv/bin/tc-oidc-verification-code" ]]; then
        TC_CLIENT_CMD=("$REPO_ROOT/core/tc_api/venv/bin/tc-oidc-verification-code")
        return 0
    fi

    if [[ -x "$REPO_ROOT/core/tc_api/venv/bin/python" ]]; then
        TC_CLIENT_CMD=("$REPO_ROOT/core/tc_api/venv/bin/python" "-m" "tc_api.cli.oidc_verification_code")
        return 0
    fi

    return 1
}

ensure_tc_api_identity_token() {
    if [[ -n "${TC_API_IDENTITY_TOKEN:-}" || -n "${TC_API_BEARER_TOKEN:-}" ]]; then
        return 0
    fi

    if [[ ! -t 0 || ! -t 1 ]]; then
        echo "TC_API_IDENTITY_TOKEN / TC_API_BEARER_TOKEN is missing, and no interactive terminal is available for OIDC login." >&2
        echo "Run this script in an interactive shell, or pre-export TC_API_IDENTITY_TOKEN / TC_API_BEARER_TOKEN." >&2
        exit 1
    fi

    if ! resolve_tc_client_cmd; then
        echo "Unable to find tc-client. Run '$REPO_ROOT/core/tc_api/setup.sh' first, or install tc-client in PATH." >&2
        exit 1
    fi

    echo "No TC_API token found. Starting interactive Sigstore OIDC login..." >&2
    local max_attempts="${TC_API_OIDC_MAX_ATTEMPTS:-3}"
    local attempt token_value reply oidc_output_file

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        oidc_output_file="$(mktemp)"
        echo "verification code: paste it when prompted below" >&2
        if "${TC_CLIENT_CMD[@]}" --operation openclaw-launch --format json | tee "$oidc_output_file"; then
            token_value="$(python3 - "$oidc_output_file" <<'PY'
import json
import re
import sys

text = open(sys.argv[1], "r", encoding="utf-8").read()
token = ""

try:
    obj = json.loads(text)
    token = (obj.get("identity_token") or "").strip()
except Exception:
    idx = text.find("{")
    if idx >= 0:
        try:
            obj = json.loads(text[idx:])
            token = (obj.get("identity_token") or "").strip()
        except Exception:
            token = ""
    if not token:
        m = re.search(r'"identity_token"\s*:\s*"([^"]+)"', text)
        if m:
            token = m.group(1).strip()

print(token)
PY
)"
            if [[ -n "$token_value" ]]; then
                rm -f "$oidc_output_file"
                export TC_API_IDENTITY_TOKEN="$token_value"
                echo "Acquired TC_API_IDENTITY_TOKEN via interactive OIDC flow." >&2
                return 0
            fi
        fi
        rm -f "$oidc_output_file"

        echo "OIDC token exchange failed (attempt ${attempt}/${max_attempts})." >&2
        echo "Common causes: verification code expired, copied the wrong value, or waited too long before pasting." >&2
        if (( attempt == max_attempts )); then
            break
        fi
        read -r -p "Retry OIDC login now? [Y/n] " reply
        if [[ "$reply" =~ ^[Nn]$ ]]; then
            break
        fi
    done

    echo "Failed to acquire TC_API_IDENTITY_TOKEN via OIDC." >&2
    exit 1
}

main() {
    require_command curl
    require_command python3

    if [[ "$OPENCLAW_BUILD_IMAGE" == "1" ]]; then
        require_command docker
        [[ -f "$OPENCLAW_DOCKERFILE" ]] || {
            echo "OpenClaw Dockerfile not found: $OPENCLAW_DOCKERFILE" >&2
            exit 1
        }
        log "Building OpenClaw image: $OPENCLAW_IMAGE_NAME"
        DOCKER_BUILDKIT="$OPENCLAW_BUILDKIT" docker build -f "$OPENCLAW_DOCKERFILE" -t "$OPENCLAW_IMAGE_NAME" "$OPENCLAW_BUILD_CONTEXT"
    fi

    if [[ "$OPENCLAW_PUSH_IMAGE" == "1" ]]; then
        require_command docker
        log "Pushing OpenClaw image"
        docker push "$OPENCLAW_IMAGE_NAME"
    fi

    auth_args=()
    if [[ -n "${TC_API_BEARER_TOKEN:-}" ]]; then
        auth_args=(-H "Authorization: Bearer ${TC_API_BEARER_TOKEN}")
    fi

    ensure_tc_api_identity_token

    payload=$(python3 - <<'PY'
import json
import os

attestation_required = os.environ.get("OPENCLAW_ATTESTATION_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}
identity_token = os.environ.get("TC_API_IDENTITY_TOKEN")
dockercmd = os.environ.get("OPENCLAW_DOCKERCMD")

payload = {
    "image_id": os.environ.get("OPENCLAW_IMAGE_ID", "openclaw-sbx"),
    "image_url": os.environ.get("OPENCLAW_IMAGE_URL", "docker://registry:5000/openclaw-sbx:latest"),
    "user_id": os.environ.get("OPENCLAW_USER_ID", "openclaw-demo"),
    "attestation_required": attestation_required,
    "metadata": {
        "workload_id": os.environ.get("OPENCLAW_WORKLOAD_ID", "openclaw-agent"),
        "service_name": os.environ.get("OPENCLAW_WORKLOAD_ID", "openclaw-agent"),
    },
}
if identity_token:
    payload["identity_token"] = identity_token
if dockercmd:
    payload["dockercmd"] = dockercmd

print(json.dumps(payload))
PY
)

    log "Submitting OpenClaw deploy-launch request to $TC_API_URL"
    response_file="$(mktemp)"
    http_code=$(curl -sS -o "$response_file" -w '%{http_code}' -X POST "${TC_API_URL}/api/deploy-launch" \
        -H 'Content-Type: application/json' \
        "${auth_args[@]}" \
        -d "$payload")

    if [[ "$http_code" == "401" && -z "${TC_API_BEARER_TOKEN:-}" ]]; then
        echo "Received 401 from tc-api, likely due short-lived OIDC token expiry. Re-acquiring token and retrying once..." >&2
        unset TC_API_IDENTITY_TOKEN
        ensure_tc_api_identity_token
        payload=$(python3 - <<'PY'
import json
import os

attestation_required = os.environ.get("OPENCLAW_ATTESTATION_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}
identity_token = os.environ.get("TC_API_IDENTITY_TOKEN")
dockercmd = os.environ.get("OPENCLAW_DOCKERCMD")

payload = {
    "image_id": os.environ.get("OPENCLAW_IMAGE_ID", "openclaw-sbx"),
    "image_url": os.environ.get("OPENCLAW_IMAGE_URL", "docker://registry:5000/openclaw-sbx:latest"),
    "user_id": os.environ.get("OPENCLAW_USER_ID", "openclaw-demo"),
    "attestation_required": attestation_required,
    "metadata": {
        "workload_id": os.environ.get("OPENCLAW_WORKLOAD_ID", "openclaw-agent"),
        "service_name": os.environ.get("OPENCLAW_WORKLOAD_ID", "openclaw-agent"),
    },
}
if identity_token:
    payload["identity_token"] = identity_token
if dockercmd:
    payload["dockercmd"] = dockercmd

print(json.dumps(payload))
PY
)
        http_code=$(curl -sS -o "$response_file" -w '%{http_code}' -X POST "${TC_API_URL}/api/deploy-launch" \
            -H 'Content-Type: application/json' \
            "${auth_args[@]}" \
            -d "$payload")
    fi

    if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
        cat "$response_file" >&2 || true
        rm -f "$response_file"
        return 1
    fi

    response="$(cat "$response_file")"
    rm -f "$response_file"

    launch_id=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["launch_id"])')
    log "OpenClaw launch_id: $launch_id"

    for ((attempt=1; attempt<=POLL_ATTEMPTS; attempt++)); do
        result=$(curl -fsS "${TC_API_URL}/api/launch-result/${launch_id}")
        status=$(printf '%s' "$result" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "unknown"))')
        printf '[step2] poll %02d/%02d status=%s\n' "$attempt" "$POLL_ATTEMPTS" "$status"

        if [[ "$status" == "success" ]]; then
            RESULT_JSON="$result" python3 - <<'PY'
import json
import os

data = json.loads(os.environ.get("RESULT_JSON", "{}"))
evidence = data.get("evidence", {})
print("[step2] OpenClaw launched by tc-api.")
print(f"[step2] workload_id={evidence.get('workload_id')}")
print(f"[step2] image_digest={evidence.get('image_digest')}")
print(f"[step2] instance_ids={evidence.get('instance_ids')}")
PY
            log "Step 2 complete"
            return 0
        fi

        if [[ "$status" == "failed" ]]; then
            printf '%s\n' "$result"
            return 1
        fi

        sleep "$POLL_INTERVAL"
    done

    echo "Timed out waiting for OpenClaw launch result" >&2
    return 1
}

main "$@"

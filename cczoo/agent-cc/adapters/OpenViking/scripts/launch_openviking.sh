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
PROVIDER_URL="${PROVIDER_URL:-http://127.0.0.1:8008}"
WORKLOAD_ID="${WORKLOAD_ID:-openviking-cmem}"
OPENVIKING_VERSION="${OPENVIKING_VERSION:-v0.4.8}"
OPENVIKING_BASE="${OPENVIKING_BASE:-ghcr.io/volcengine/openviking@sha256:27d3c97bddbe81f31d2c5af1f31e9d504b5928506c88f559a23faf86358169b7}"
IMAGE_NAME="${IMAGE_NAME:-localhost:5000/openviking:${OPENVIKING_VERSION}}"
IMAGE_URL="${IMAGE_URL:-docker://registry:5000/openviking:${OPENVIKING_VERSION}}"
IMAGE_ID="${IMAGE_ID:-openviking-cmem}"
OPENVIKING_USE_LUKS="${OPENVIKING_USE_LUKS:-1}"
OPENVIKING_LUKS_MOUNT_ROOT="${OPENVIKING_LUKS_MOUNT_ROOT:-/home/encrypted_storage}"
OPENVIKING_LUKS_SUBDIR="${OPENVIKING_LUKS_SUBDIR:-openviking}"
OPENVIKING_CONTAINER_STATE_DIR="${OPENVIKING_CONTAINER_STATE_DIR:-/app/.openviking}"
ATTESTATION_REQUIRED="${ATTESTATION_REQUIRED:-false}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-40}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-60}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"
AUTO_START_INFRA="${AUTO_START_INFRA:-1}"
DOCKERFILE_PATH="${DOCKERFILE_PATH:-$REPO_ROOT/adapters/OpenViking/configs/Dockerfile.openviking}"
COMPOSE_FILE_PATH="${COMPOSE_FILE_PATH:-$REPO_ROOT/adapters/OpenViking/configs/docker-compose.tc-api.yml}"

export IMAGE_URL IMAGE_ID WORKLOAD_ID ATTESTATION_REQUIRED

wait_http() {
    local url="$1"
    local name="$2"
    local attempt

    for ((attempt=1; attempt<=WAIT_ATTEMPTS; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            echo "$name is ready: $url"
            return 0
        fi
        sleep "$WAIT_INTERVAL"
    done

    echo "$name did not become ready: $url" >&2
    exit 1
}

resolve_compose_cmd() {
    if command -v docker-compose >/dev/null 2>&1; then
        COMPOSE_CMD=("$(command -v docker-compose)")
        return 0
    fi

    if docker compose version >/dev/null 2>&1; then
        COMPOSE_CMD=(docker compose)
        return 0
    fi

    return 1
}

ensure_infra_stack() {
    if [[ "$AUTO_START_INFRA" != "1" ]]; then
        echo "AUTO_START_INFRA=0, skipping automatic startup of registry/tc-api/argus-provider."
        return 0
    fi

    if [[ ! -f "$COMPOSE_FILE_PATH" ]]; then
        echo "Missing compose file: $COMPOSE_FILE_PATH" >&2
        exit 1
    fi

    if ! resolve_compose_cmd; then
        echo "docker-compose (or docker compose) is required to auto-start registry/tc-api/argus-provider." >&2
        echo "Install compose tooling, or set AUTO_START_INFRA=0 and start the stack manually first." >&2
        exit 1
    fi

    echo "[0/5] Ensuring registry + tc-api + argus-provider are running"
    "${COMPOSE_CMD[@]}" -f "$COMPOSE_FILE_PATH" up -d registry tc-api argus-provider

    wait_http "$TC_API_URL/" "tc-api"
    wait_http "$PROVIDER_URL/health" "argus-provider"
}

prepare_openviking_storage() {
    export OPENVIKING_HOST_DATA_DIR=""


    export OPENVIKING_DOCKER_CMD="docker run -d --name=agentcc-openviking-service --label=argus.workload=${WORKLOAD_ID} --publish=127.0.0.1:1933:1933 --env=OPENVIKING_CONFIG_FILE=${OPENVIKING_CONTAINER_STATE_DIR}/ov.conf --env=OPENVIKING_WITH_BOT=0"

    if [[ "$OPENVIKING_USE_LUKS" != "1" ]]; then
        echo "OPENVIKING_USE_LUKS=0, using container-local storage only." >&2
    else
        if ! command -v mountpoint >/dev/null 2>&1; then
            echo "mountpoint command is required when OPENVIKING_USE_LUKS=1." >&2
            exit 1
        fi

        if ! mountpoint -q "$OPENVIKING_LUKS_MOUNT_ROOT"; then
            echo "LUKS mount root is not mounted: $OPENVIKING_LUKS_MOUNT_ROOT" >&2
            echo "Use cczoo/openclaw-cc/luks_tools/mount_encrypted_vfs.sh first, or set OPENVIKING_USE_LUKS=0." >&2
            exit 1
        fi

        export OPENVIKING_HOST_DATA_DIR="$OPENVIKING_LUKS_MOUNT_ROOT/$OPENVIKING_LUKS_SUBDIR"
        mkdir -p "$OPENVIKING_HOST_DATA_DIR"
        if [[ ! -f "$OPENVIKING_HOST_DATA_DIR/ov.conf" ]]; then
            echo "Missing OpenViking configuration: $OPENVIKING_HOST_DATA_DIR/ov.conf" >&2
            echo "Create it with the required model and API-key configuration before launching." >&2
            exit 1
        fi
        export OPENVIKING_DOCKER_CMD="$OPENVIKING_DOCKER_CMD --volume=${OPENVIKING_HOST_DATA_DIR}:${OPENVIKING_CONTAINER_STATE_DIR}"
        echo "OpenViking encrypted storage: host=${OPENVIKING_HOST_DATA_DIR} -> container=${OPENVIKING_CONTAINER_STATE_DIR}" >&2
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
        if "${TC_CLIENT_CMD[@]}" --operation openviking-launch --format json | tee "$oidc_output_file"; then
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

if [[ -z "$OPENVIKING_VERSION" ]]; then
    echo "OPENVIKING_VERSION is required and must identify a tested OpenViking release." >&2
    exit 1
fi

if [[ -z "$OPENVIKING_BASE" ]]; then
    echo "OPENVIKING_BASE is required and must be a pinned official OpenViking image digest." >&2
    exit 1
fi

if [[ "$OPENVIKING_BASE" != *@sha256:* ]]; then
    echo "OPENVIKING_BASE must use a pinned image digest (@sha256:<digest>)." >&2
    exit 1
fi

if [[ ! -f "$DOCKERFILE_PATH" ]]; then
    echo "Missing Dockerfile: $DOCKERFILE_PATH" >&2
    exit 1
fi

ensure_infra_stack
prepare_openviking_storage

auth_args=()
if [[ -n "${TC_API_BEARER_TOKEN:-}" ]]; then
    auth_args=(-H "Authorization: Bearer ${TC_API_BEARER_TOKEN}")
fi

echo "[1/5] Building OpenViking workload image: ${IMAGE_NAME}"
docker build --build-arg "OPENVIKING_BASE=${OPENVIKING_BASE}" -t "${IMAGE_NAME}" -f "${DOCKERFILE_PATH}" "${REPO_ROOT}"

echo "[2/5] Pushing image to local registry"
docker push "$IMAGE_NAME"

echo "     tc-api pull reference: ${IMAGE_URL}"

ensure_tc_api_identity_token

payload=$(python3 - <<'PY'
import json
import os

attestation_required = os.environ.get("ATTESTATION_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}
identity_token = os.environ.get("TC_API_IDENTITY_TOKEN")

payload = {
    "image_id": os.environ.get("IMAGE_ID", "openviking-cmem"),
    "image_url": os.environ.get("IMAGE_URL", "docker://registry:5000/openviking:v0.4.8"),
    "user_id": os.environ.get("TC_API_USER_ID", "openviking-demo"),
    "attestation_required": attestation_required,
    "metadata": {
        "workload_id": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
        "service_name": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
    },
}
if identity_token:
    payload["identity_token"] = identity_token
dockercmd = os.environ.get("OPENVIKING_DOCKER_CMD", "").strip()
if dockercmd:
    payload["dockercmd"] = dockercmd
print(json.dumps(payload))
PY
)

echo "[3/5] Submitting deploy-launch request to ${TC_API_URL}"
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

attestation_required = os.environ.get("ATTESTATION_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}
identity_token = os.environ.get("TC_API_IDENTITY_TOKEN")

payload = {
    "image_id": os.environ.get("IMAGE_ID", "openviking-cmem"),
    "image_url": os.environ.get("IMAGE_URL", "docker://registry:5000/openviking:v0.4.8"),
    "user_id": os.environ.get("TC_API_USER_ID", "openviking-demo"),
    "attestation_required": attestation_required,
    "metadata": {
        "workload_id": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
        "service_name": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
    },
}
if identity_token:
    payload["identity_token"] = identity_token
dockercmd = os.environ.get("OPENVIKING_DOCKER_CMD", "").strip()
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
    exit 1
fi

response="$(cat "$response_file")"
rm -f "$response_file"

launch_id=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["launch_id"])')
echo "Launch ID: ${launch_id}"

echo "[4/5] Polling launch result"
for ((attempt=1; attempt<=POLL_ATTEMPTS; attempt++)); do
    result=$(curl -fsS "${TC_API_URL}/api/launch-result/${launch_id}")
    status=$(printf '%s' "$result" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "unknown"))')
    printf '  attempt %02d/%02d status=%s\n' "$attempt" "$POLL_ATTEMPTS" "$status"
    if [[ "$status" == "success" ]]; then
        RESULT_JSON="$result" python3 - <<'PY'
import json
import os

data = json.loads(os.environ.get("RESULT_JSON", "{}"))
evidence = data.get("evidence", {})
print("Launch completed successfully.")
print(f"  workload_id: {evidence.get('workload_id')}")
print(f"  image_digest: {evidence.get('image_digest')}")
print(f"  instance_ids: {evidence.get('instance_ids')}")
print("")
print("Use these provider env values when debugging outside Compose:")
print(f"  ARGUS_WORKLOAD_IDENTITY={evidence.get('workload_id')}")
print(f"  ARGUS_SERVICE_ID={evidence.get('workload_id')}")
print(f"  TC_API_WORKLOAD_ID={evidence.get('workload_id')}")
PY
        exit 0
    fi
    if [[ "$status" == "failed" ]]; then
        printf '%s\n' "$result"
        exit 1
    fi
    sleep "$POLL_INTERVAL"
done

echo "Timed out waiting for launch ${launch_id}" >&2
exit 1

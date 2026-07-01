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
WORKLOAD_ID="${WORKLOAD_ID:-openviking-cmem}"
IMAGE_NAME="${IMAGE_NAME:-localhost:5000/openviking-cmem:latest}"
IMAGE_URL="${IMAGE_URL:-docker://registry:5000/openviking-cmem:latest}"
IMAGE_ID="${IMAGE_ID:-openviking-cmem}"
ATTESTATION_REQUIRED="${ATTESTATION_REQUIRED:-false}"
POLL_INTERVAL="${POLL_INTERVAL:-3}"
POLL_ATTEMPTS="${POLL_ATTEMPTS:-40}"
DOCKERFILE_PATH="${DOCKERFILE_PATH:-$SCRIPT_DIR/Dockerfile.tc-api-workload}"

if [[ -z "${TC_API_IDENTITY_TOKEN:-}" && -z "${TC_API_BEARER_TOKEN:-}" ]]; then
    echo "Set TC_API_IDENTITY_TOKEN or TC_API_BEARER_TOKEN before submitting deploy-launch." >&2
    exit 1
fi

if [[ ! -f "$DOCKERFILE_PATH" ]]; then
    echo "Missing Dockerfile: $DOCKERFILE_PATH" >&2
    exit 1
fi

auth_args=()
identity_json='null'
if [[ -n "${TC_API_BEARER_TOKEN:-}" ]]; then
    auth_args=(-H "Authorization: Bearer ${TC_API_BEARER_TOKEN}")
fi
if [[ -n "${TC_API_IDENTITY_TOKEN:-}" ]]; then
    identity_json=$(python3 -c 'import json, os; print(json.dumps(os.environ["TC_API_IDENTITY_TOKEN"]))')
fi

echo "[1/4] Building OpenViking workload image: ${IMAGE_NAME}"
docker build -t "$IMAGE_NAME" -f "$DOCKERFILE_PATH" "$REPO_ROOT"

echo "[2/4] Pushing image to local registry"
docker push "$IMAGE_NAME"

echo "     tc-api pull reference: ${IMAGE_URL}"

payload=$(python3 - <<'PY'
import json
import os

attestation_required = os.environ.get("ATTESTATION_REQUIRED", "false").lower() in {"1", "true", "yes", "on"}
identity_token = os.environ.get("TC_API_IDENTITY_TOKEN")

payload = {
    "image_id": os.environ.get("IMAGE_ID", "openviking-cmem"),
    "image_url": os.environ.get("IMAGE_URL", "docker://registry:5000/openviking-cmem:latest"),
    "user_id": os.environ.get("TC_API_USER_ID", "openviking-demo"),
    "attestation_required": attestation_required,
    "metadata": {
        "workload_id": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
        "service_name": os.environ.get("WORKLOAD_ID", "openviking-cmem"),
    },
}
if identity_token:
    payload["identity_token"] = identity_token
print(json.dumps(payload))
PY
)

echo "[3/4] Submitting deploy-launch request to ${TC_API_URL}"
response=$(curl -fsS -X POST "${TC_API_URL}/api/deploy-launch" \
    -H 'Content-Type: application/json' \
    "${auth_args[@]}" \
    -d "$payload")

launch_id=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["launch_id"])')
echo "Launch ID: ${launch_id}"

echo "[4/4] Polling launch result"
for ((attempt=1; attempt<=POLL_ATTEMPTS; attempt++)); do
    result=$(curl -fsS "${TC_API_URL}/api/launch-result/${launch_id}")
    status=$(printf '%s' "$result" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status", "unknown"))')
    printf '  attempt %02d/%02d status=%s\n' "$attempt" "$POLL_ATTEMPTS" "$status"
    if [[ "$status" == "success" ]]; then
        printf '%s\n' "$result" | python3 - <<'PY'
import json
import sys

data = json.load(sys.stdin)
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
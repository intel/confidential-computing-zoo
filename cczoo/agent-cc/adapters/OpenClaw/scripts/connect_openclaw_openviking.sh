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

TARGET_URI="${TARGET_URI:-http://127.0.0.1:1933}"
OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-agentcc-openclaw-sbx-gateway}"
OPENCLAW_PLUGIN_SPEC="${OPENCLAW_PLUGIN_SPEC:-clawhub:@openviking/openclaw-plugin}"
OPENCLAW_INSTALL_PLUGIN="${OPENCLAW_INSTALL_PLUGIN:-1}"
OPENVIKING_API_KEY="${OPENVIKING_API_KEY:-}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-60}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"

log() {
    printf '[openviking-plugin] %s\n' "$*"
}

require_command() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required command: $1" >&2
        exit 1
    fi
}

wait_http() {
    local url="$1"
    local name="$2"
    local attempt

    for ((attempt=1; attempt<=WAIT_ATTEMPTS; attempt++)); do
        if curl -fsS "$url" >/dev/null 2>&1; then
            log "$name is ready: $url"
            return 0
        fi
        sleep "$WAIT_INTERVAL"
    done

    echo "$name did not become ready: $url" >&2
    exit 1
}

main() {
    require_command curl
    require_command docker

    if [[ -z "$OPENVIKING_API_KEY" ]]; then
        echo "OPENVIKING_API_KEY must contain a non-root OpenViking user key." >&2
        exit 1
    fi

    wait_http "$TARGET_URI/health" "openviking health"
    wait_http "$TARGET_URI/ready" "openviking readiness"

    if [[ "$OPENCLAW_INSTALL_PLUGIN" == "1" ]]; then
        log "Installing the OpenViking OpenClaw plugin"
        docker exec "$OPENCLAW_CONTAINER" openclaw plugins install "$OPENCLAW_PLUGIN_SPEC"
    fi

    log "Configuring the OpenViking context engine"
    docker exec "$OPENCLAW_CONTAINER" openclaw openviking setup \
        --base-url "$TARGET_URI" \
        --api-key "$OPENVIKING_API_KEY" \
        --json

    log "Restarting the OpenClaw gateway"
    docker restart "$OPENCLAW_CONTAINER" >/dev/null

    log "Verifying the OpenViking plugin status"
    docker exec "$OPENCLAW_CONTAINER" openclaw openviking status --json
}

main "$@"

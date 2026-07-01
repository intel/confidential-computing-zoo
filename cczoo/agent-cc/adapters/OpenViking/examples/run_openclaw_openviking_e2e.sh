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
OPENCLAW_DIR="$REPO_ROOT/adapters/OpenClaw/examples"
ARGUS_DIR="$REPO_ROOT/core/argus"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.tc-api.yml"
LAUNCH_SCRIPT="$SCRIPT_DIR/launch_openviking_via_tc_api.sh"

TC_API_URL="${TC_API_URL:-http://127.0.0.1:8000}"
PROVIDER_URL="${PROVIDER_URL:-http://127.0.0.1:8008}"
GUARD_URL="${GUARD_URL:-http://127.0.0.1:8007}"
TARGET_URI="${TARGET_URI:-http://127.0.0.1:8010}"
TARGET_SERVICE_NAME="${TARGET_SERVICE_NAME:-openviking-cmem}"
OPENCLAW_PYTHON="${OPENCLAW_PYTHON:-python3}"
RUST_LOG="${RUST_LOG:-info}"
FORCE_LAUNCH="${FORCE_LAUNCH:-0}"
SKIP_LAUNCH="${SKIP_LAUNCH:-0}"
GUARD_LOG_FILE="${GUARD_LOG_FILE:-$ARGUS_DIR/guard-real.log}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-60}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"

log() {
    printf '[e2e] %s\n' "$*"
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

ensure_guard_binary() {
    if [[ -x "$ARGUS_DIR/target/release/argus-guard" ]]; then
        return 0
    fi
    log "Building argus-guard release binary"
    (cd "$ARGUS_DIR" && cargo build --release --bin argus-guard)
}

start_compose_stack() {
    log "Starting registry + tc-api + argus-provider"
    docker-compose -f "$COMPOSE_FILE" up -d --build registry tc-api argus-provider
    wait_http "$TC_API_URL/" "tc-api"
    wait_http "$PROVIDER_URL/health" "argus-provider"
}

launch_workload_if_needed() {
    if [[ "$SKIP_LAUNCH" == "1" ]]; then
        log "Skipping workload launch because SKIP_LAUNCH=1"
        return 0
    fi

    if [[ "$FORCE_LAUNCH" != "1" ]] && curl -fsS "$TARGET_URI/health" >/dev/null 2>&1; then
        log "OpenViking workload is already healthy at $TARGET_URI; skipping launch"
        return 0
    fi

    if [[ -z "${TC_API_IDENTITY_TOKEN:-}" && -z "${TC_API_BEARER_TOKEN:-}" ]]; then
        echo "Set TC_API_IDENTITY_TOKEN or TC_API_BEARER_TOKEN before launching the workload." >&2
        exit 1
    fi

    log "Launching OpenViking workload through tc-api"
    (
        cd "$SCRIPT_DIR"
        TC_API_URL="$TC_API_URL" \
        TARGET_URI="$TARGET_URI" \
        TARGET_SERVICE_NAME="$TARGET_SERVICE_NAME" \
        "$LAUNCH_SCRIPT"
    )
}

start_real_guard() {
    ensure_guard_binary
    log "Restarting Argus Guard in real-verifier mode"
    pkill -f '/argus-guard' 2>/dev/null || true
    (
        cd "$ARGUS_DIR"
        nohup env -u ARGUS_ALLOW_MOCK_VERIFIER \
            EVIDENCE_ENDPOINT="$PROVIDER_URL" \
            RUST_LOG="$RUST_LOG" \
            ./target/release/argus-guard >"$GUARD_LOG_FILE" 2>&1 &
        echo $! > .argus-guard.pid
    )
    wait_http "$GUARD_URL/health" "argus-guard"
}

run_openclaw() {
    log "Running OpenClaw end-to-end example"
    (
        cd "$OPENCLAW_DIR"
        TARGET_URI="$TARGET_URI" \
        TARGET_SERVICE_NAME="$TARGET_SERVICE_NAME" \
        "$OPENCLAW_PYTHON" openclaw_agent.py
    )
}

main() {
    require_command docker
    require_command docker-compose
    require_command curl
    require_command "$OPENCLAW_PYTHON"
    require_command cargo

    start_compose_stack
    launch_workload_if_needed
    wait_http "$TARGET_URI/health" "openviking-workload"
    start_real_guard
    run_openclaw

    log "Completed real quote end-to-end flow"
    log "Guard log: $GUARD_LOG_FILE"
}

main "$@"
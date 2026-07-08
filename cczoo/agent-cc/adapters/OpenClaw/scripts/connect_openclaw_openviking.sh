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
ARGUS_DIR="$REPO_ROOT/core/argus"

PROVIDER_URL="${PROVIDER_URL:-http://127.0.0.1:8008}"
GUARD_URL="${GUARD_URL:-http://127.0.0.1:8007}"
TARGET_URI="${TARGET_URI:-http://127.0.0.1:8010}"
TARGET_SERVICE_NAME="${TARGET_SERVICE_NAME:-openviking-cmem}"
OPENCLAW_PYTHON="${OPENCLAW_PYTHON:-python3}"
RUST_LOG="${RUST_LOG:-info}"
GUARD_LOG_FILE="${GUARD_LOG_FILE:-$ARGUS_DIR/guard-real.log}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-60}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"

log() {
    printf '[step3] %s\n' "$*"
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

main() {
    require_command curl
    require_command cargo
    require_command "$OPENCLAW_PYTHON"

    wait_http "$PROVIDER_URL/health" "argus-provider"
    wait_http "$TARGET_URI/health" "openviking-workload"

    ensure_guard_binary

    log "Restarting argus-guard in real verifier mode"
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

    log "Running OpenClaw caller flow through Argus"
    (
        cd "$SCRIPT_DIR"
        TARGET_URI="$TARGET_URI" \
        TARGET_SERVICE_NAME="$TARGET_SERVICE_NAME" \
        "$OPENCLAW_PYTHON" openclaw_agent.py
    )

    log "Step 3 complete"
    log "Guard log: $GUARD_LOG_FILE"
}

main "$@"

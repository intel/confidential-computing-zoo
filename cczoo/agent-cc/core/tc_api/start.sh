#!/bin/bash

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

# TC API Startup Script

set -euo pipefail

# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/scripts/common.sh"
tc_api_cd_repo_root
SCRIPT_DIR="$TC_API_REPO_ROOT"

DOCKERHUB_ACCOUNT="<your dockerhub account>"
PID_DIR="$SCRIPT_DIR/logs/pids"
TC_API_PID_FILE="$PID_DIR/tc_api.pid"
TRUCON_PID_FILE="$PID_DIR/trucon.pid"
DOCKTAP_PID_FILE="$PID_DIR/docktap.pid"
TC_API_PID=""
TRUCON_PID=""
DOCKTAP_PID=""
START_MODE="production"
COMMAND="start"
RESET_STATE="false"

TRUCON_QUEUE_DIR="${TRUCON_QUEUE_DIR:-/dev/shm/tc_api_queue}"
TRUCON_DB_PATH="${COMMIT_QUEUE_DB:-$TRUCON_QUEUE_DIR/queue.db}"
TRUCON_LEGACY_DB_PATH="/dev/shm/commit_queue.db"
TRUCON_LOCK_PATH="${TRUCON_LOCK_PATH:-$TRUCON_QUEUE_DIR/trucon.lock}"
DOCKTAP_WORKLOAD_DB_PATH="${DOCKTAP_WORKLOAD_DB:-/dev/shm/docktap/container_map.db}"

echo "Login in Dokcerhub"
if docker info 2>/dev/null | grep -q "Username:"; then
	echo "Docker logined"
else
	docker login -u $DOCKERHUB_ACCOUNT
fi

echo "Starting TC API Service..."

usage() {
        cat <<'EOF'
Usage:
    ./start.sh
    ./start.sh start [dev]
    ./start.sh stop
    ./start.sh restart [dev] [--reset-state]
    ./start.sh reset-state

Examples:
    ./start.sh
    ./start.sh dev
    ./start.sh restart
    ./start.sh restart dev
    ./start.sh restart --reset-state
    ./start.sh reset-state
EOF
}

remove_state_file_family() {
    local base_path="$1"

    rm -f "$base_path" "$base_path-shm" "$base_path-wal"
}

reset_local_state() {
    echo "Resetting local TruCon and Docktap state..."

    remove_state_file_family "$TRUCON_DB_PATH"
    if [[ "$TRUCON_LEGACY_DB_PATH" != "$TRUCON_DB_PATH" ]]; then
        remove_state_file_family "$TRUCON_LEGACY_DB_PATH"
    fi
    rm -f "$TRUCON_LOCK_PATH"
    rmdir "$TRUCON_QUEUE_DIR" 2>/dev/null || true

    remove_state_file_family "$DOCKTAP_WORKLOAD_DB_PATH"
    if [[ -n "$DOCKTAP_WORKLOAD_DB_PATH" ]]; then
        rmdir "$(dirname "$DOCKTAP_WORKLOAD_DB_PATH")" 2>/dev/null || true
    fi

    echo "✓ Local TruCon and Docktap state cleared."
}

startup_baseline_required() {
    local raw_value="${INIT_DEFAULT_CHAIN_ON_STARTUP:-true}"
    raw_value="$(printf '%s' "$raw_value" | tr '[:upper:]' '[:lower:]')"
    [[ "$raw_value" == "1" || "$raw_value" == "true" || "$raw_value" == "yes" || "$raw_value" == "on" ]]
}

has_reusable_sigstore_token() {
    "$PYTHON_BIN" - <<'PY'
from tc_api.identity.sigstore_identity import resolve_sigstore_identity_token

token = resolve_sigstore_identity_token(
    operation="baseline",
    allow_interactive=False,
    min_ttl_seconds=15,
    require_token=False,
    suppress_warning=True,
)
raise SystemExit(0 if token else 1)
PY
}

ensure_startup_sigstore_token() {
    if ! startup_baseline_required; then
        return 0
    fi

    if [[ -t 0 && -t 1 ]]; then
        if has_reusable_sigstore_token; then
            echo "Refreshing Sigstore identity token for default-chain baseline startup."
        else
            echo "No reusable Sigstore identity token found for default-chain baseline startup."
        fi
        "$PYTHON_BIN" -m tc_api.cli.oidc_verification_code --operation baseline --format none

        if ! has_reusable_sigstore_token; then
            echo "Error: Sigstore identity token acquisition did not produce a reusable token for baseline startup." >&2
            exit 1
        fi
        return 0
    fi

    if has_reusable_sigstore_token; then
        return 0
    fi

    echo "Error: default-chain baseline startup requires a reusable Sigstore identity token, but no interactive terminal is available." >&2
    echo "Run '$PYTHON_BIN -m tc_api.cli.oidc_verification_code --operation baseline --format export' first, or set TC_API_REAL_REKOR_IDENTITY_TOKEN." >&2
    exit 1
}

pid_is_running() {
    local pid="$1"
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

read_pid_file() {
    local pid_file="$1"
    if [[ -f "$pid_file" ]]; then
        tr -d '[:space:]' < "$pid_file"
    fi
}

remove_pid_file_if_stale() {
    local pid_file="$1"
    local pid
    pid=$(read_pid_file "$pid_file")
    if [[ -n "$pid" ]] && ! pid_is_running "$pid"; then
        rm -f "$pid_file"
    fi
}

iter_matching_pids() {
    local match_a="$1"
    local match_b="${2:-}"
    local proc_dir cmdline_path raw cmdline pid

    for proc_dir in /proc/[0-9]*; do
        [[ -d "$proc_dir" ]] || continue
        cmdline_path="$proc_dir/cmdline"
        [[ -r "$cmdline_path" ]] || continue
        raw=$(tr '\000' ' ' < "$cmdline_path" 2>/dev/null || true)
        [[ -n "$raw" ]] || continue
        if [[ "$raw" == *"$match_a"* ]] && { [[ -z "$match_b" ]] || [[ "$raw" == *"$match_b"* ]]; }; then
            pid="${proc_dir##*/}"
            printf '%s\n' "$pid"
        fi
    done
}

stop_pid() {
    local name="$1"
    local pid="$2"

    [[ -n "$pid" ]] || return 0
    if ! pid_is_running "$pid"; then
        return 0
    fi

    echo "Stopping $name (PID: $pid)..."
    kill -TERM "$pid" 2>/dev/null || true
    for _ in $(seq 1 30); do
        if ! pid_is_running "$pid"; then
            break
        fi
        sleep 1
    done
    if pid_is_running "$pid"; then
        echo "$name did not exit after SIGTERM; sending SIGKILL..."
        kill -KILL "$pid" 2>/dev/null || true
    fi
}

stop_pid_from_file() {
    local name="$1"
    local pid_file="$2"
    local pid

    pid=$(read_pid_file "$pid_file")
    if [[ -z "$pid" ]]; then
        return 0
    fi

    stop_pid "$name" "$pid"

    rm -f "$pid_file"
}

stop_matching_processes() {
    local name="$1"
    local match_a="$2"
    local match_b="${3:-}"
    local pid

    while IFS= read -r pid; do
        stop_pid "$name" "$pid"
    done < <(iter_matching_pids "$match_a" "$match_b")
}

stop_services() {
    mkdir -p "$PID_DIR"
    remove_pid_file_if_stale "$TC_API_PID_FILE"
    remove_pid_file_if_stale "$DOCKTAP_PID_FILE"
    remove_pid_file_if_stale "$TRUCON_PID_FILE"

    stop_pid_from_file "TC API" "$TC_API_PID_FILE"
    stop_pid_from_file "Docktap" "$DOCKTAP_PID_FILE"
    stop_pid_from_file "TruCon" "$TRUCON_PID_FILE"

    stop_matching_processes "TC API" "tc_api.api.app:app" "--port ${PORT:-8000}"
    stop_matching_processes "Docktap" "tc_api.docktap.main" "${DOCKTAP_SOCKET:-/var/run/docktap/docker.sock}"
    stop_matching_processes "TruCon" "tc_api.trucon.app:app" "--port ${TRUCON_PORT:-8001}"
}

cleanup() {
    local exit_code=$?

    if [[ -n "$TC_API_PID" ]]; then
        stop_pid_from_file "TC API" "$TC_API_PID_FILE"
        TC_API_PID=""
    fi
    if [[ -n "$DOCKTAP_PID" ]]; then
        stop_pid_from_file "Docktap" "$DOCKTAP_PID_FILE"
        DOCKTAP_PID=""
    fi
    if [[ -n "$TRUCON_PID" ]]; then
        stop_pid_from_file "TruCon" "$TRUCON_PID_FILE"
        TRUCON_PID=""
    fi

    exit "$exit_code"
}

case "${1:-start}" in
    start)
        COMMAND="start"
        if [[ "${2:-}" == "dev" ]]; then
            START_MODE="dev"
        elif [[ -n "${2:-}" ]]; then
            echo "Error: unsupported start mode '${2}'" >&2
            usage >&2
            exit 1
        fi
        ;;
    dev)
        COMMAND="start"
        START_MODE="dev"
        ;;
    stop)
        COMMAND="stop"
        if [[ $# -gt 1 ]]; then
            echo "Error: stop does not accept extra arguments" >&2
            usage >&2
            exit 1
        fi
        ;;
    restart)
        COMMAND="restart"
        shift
        while [[ $# -gt 0 ]]; do
            case "$1" in
                dev)
                    START_MODE="dev"
                    ;;
                --reset-state)
                    RESET_STATE="true"
                    ;;
                *)
                    echo "Error: unsupported restart argument '$1'" >&2
                    usage >&2
                    exit 1
                    ;;
            esac
            shift
        done
        ;;
    reset-state)
        COMMAND="reset-state"
        if [[ $# -gt 1 ]]; then
            echo "Error: reset-state does not accept extra arguments" >&2
            usage >&2
            exit 1
        fi
        ;;
    -h|--help|help)
        usage
        exit 0
        ;;
    *)
        echo "Error: unsupported command '${1}'" >&2
        usage >&2
        exit 1
        ;;
esac

if [[ "$COMMAND" == "stop" ]]; then
    stop_services
    echo "All services stopped."
    exit 0
fi

if [[ "$COMMAND" == "reset-state" ]]; then
    stop_services
    reset_local_state
    exit 0
fi

if [[ "$COMMAND" == "restart" ]]; then
    stop_services
    if [[ "$RESET_STATE" == "true" ]]; then
        reset_local_state
    fi
fi

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "Error: Docker is not installed or not in PATH"
    exit 1
fi

# Check if required tools are available (optional check)
check_tool() {
    if command -v $1 &> /dev/null; then
        echo "✓ $1 is available"
    else
        echo "⚠ Warning: $1 is not installed. Some features may not work."
    fi
}

echo "Checking external tools..."
check_tool cosign
check_tool syft  
check_tool skopeo

# Check for active swap to prevent memory-backed DB leaks
if swapon --show | grep -q "/"; then
    echo "⚠ Warning: Memory swapping is active! The ephemeral SQLite queue in /dev/shm may leak to disk."
    if [ "$STRICT_MODE" = "true" ]; then
        echo "Error: STRICT_MODE requires swap to be disabled. Aborting."
        exit 1
    fi
fi

# Create necessary directories
mkdir -p uploads builds logs /dev/shm
mkdir -p "$PID_DIR"

remove_pid_file_if_stale "$TC_API_PID_FILE"
remove_pid_file_if_stale "$DOCKTAP_PID_FILE"
remove_pid_file_if_stale "$TRUCON_PID_FILE"

if [[ -f "$TC_API_PID_FILE" || -f "$DOCKTAP_PID_FILE" || -f "$TRUCON_PID_FILE" ]]; then
    echo "Error: existing tc_api/trucon/docktap processes are already recorded. Run './start.sh stop' or './start.sh restart'." >&2
    exit 1
fi

# Set default environment variables if not set
export HOST=${HOST:-0.0.0.0}
export PORT=${PORT:-8000}
export TRUCON_PORT=${TRUCON_PORT:-8001}
export TRUCON_RTMR_INDEX=${TRUCON_RTMR_INDEX:-2}
export TC_API_WORKERS=${TC_API_WORKERS:-1}
export DOCKTAP_SOCKET=${DOCKTAP_SOCKET:-/var/run/docktap/docker.sock}
export DOCKTAP_LOG_FILE=${DOCKTAP_LOG_FILE:-$PWD/logs/docktap-latest.log}
export TRUCON_LOG_FILE=${TRUCON_LOG_FILE:-$PWD/logs/trucon-latest.log}
export DOCKTAP_REQUIRE_ATTESTATION=${DOCKTAP_REQUIRE_ATTESTATION:-1}
export TRUCON_UDS_PATH=${TRUCON_UDS_PATH:-/var/run/trucon/trucon.sock}
export DEBUG=${DEBUG:-false}
export TRUCON_AUTH_DISABLED=${TRUCON_AUTH_DISABLED:-false}
export INIT_DEFAULT_CHAIN_ON_STARTUP=${INIT_DEFAULT_CHAIN_ON_STARTUP:-true}
export PYTHON_BIN=$(tc_api_default_python_bin)
tc_api_prepend_repo_root_to_pythonpath

if [ "$DOCKTAP_REQUIRE_ATTESTATION" = "1" ]; then
    export DOCKTAP_ATTESTATION_API_URL=${DOCKTAP_ATTESTATION_API_URL:-http://127.0.0.1:${PORT}}
    export DOCKTAP_ATTESTATION_BROWSER_BASE_URL=${DOCKTAP_ATTESTATION_BROWSER_BASE_URL:-$DOCKTAP_ATTESTATION_API_URL}
fi

# Create Docktap proxy socket directory
DOCKTAP_SOCKET_DIR=$(dirname "$DOCKTAP_SOCKET")
mkdir -p "$DOCKTAP_SOCKET_DIR"

# Create TruCon socket directory
TRUCON_SOCKET_DIR=$(dirname "$TRUCON_UDS_PATH")
mkdir -p "$TRUCON_SOCKET_DIR"

# Generate a session-scoped service token for TruCon authentication
if [ -z "${TRUCON_SERVICE_TOKEN:-}" ]; then
    export TRUCON_SERVICE_TOKEN=$($PYTHON_BIN -c "import secrets; print(secrets.token_urlsafe(32))")
    echo "✓ Generated TRUCON_SERVICE_TOKEN for this session"
fi

echo "Starting TruCon (single-instance sequencer) on port $TRUCON_PORT..."
mkdir -p "$(dirname "$TRUCON_LOG_FILE")"
: > "$TRUCON_LOG_FILE"
"$PYTHON_BIN" -m uvicorn tc_api.trucon.app:app --host 0.0.0.0 --port $TRUCON_PORT --workers 1 >> "$TRUCON_LOG_FILE" 2>&1 &
TRUCON_PID=$!
echo "$TRUCON_PID" > "$TRUCON_PID_FILE"

# Wait briefly for TruCon to be ready
sleep 2
if ! kill -0 $TRUCON_PID 2>/dev/null; then
    echo "Error: TruCon failed to start"
    rm -f "$TRUCON_PID_FILE"
    exit 1
fi

export TRUCON_URL="http://127.0.0.1:${TRUCON_PORT}"
echo "✓ TruCon started (PID: $TRUCON_PID)"
echo "  TruCon log file: $TRUCON_LOG_FILE"

echo "Starting Docktap (Docker proxy sidecar) on $DOCKTAP_SOCKET..."
mkdir -p "$(dirname "$DOCKTAP_LOG_FILE")"
: > "$DOCKTAP_LOG_FILE"
"$PYTHON_BIN" -m tc_api.docktap.main --socket-path "$DOCKTAP_SOCKET" --docker-socket-path /var/run/docker.sock >> "$DOCKTAP_LOG_FILE" 2>&1 &
DOCKTAP_PID=$!
echo "$DOCKTAP_PID" > "$DOCKTAP_PID_FILE"

# Wait briefly for Docktap to be ready
sleep 2
if ! kill -0 $DOCKTAP_PID 2>/dev/null; then
    echo "Error: Docktap failed to start"
    rm -f "$DOCKTAP_PID_FILE"
    kill -TERM $TRUCON_PID 2>/dev/null || true
    exit 1
fi
echo "✓ Docktap started (PID: $DOCKTAP_PID)"
if [ "$DOCKTAP_REQUIRE_ATTESTATION" = "1" ]; then
    echo "  Attestation gate: enabled"
    echo "  Attestation API URL: $DOCKTAP_ATTESTATION_API_URL"
    echo "  Browser base URL: $DOCKTAP_ATTESTATION_BROWSER_BASE_URL"
else
    echo "  Attestation gate: disabled"
fi
echo "  Docktap log file: $DOCKTAP_LOG_FILE"
echo "  Use 'export DOCKER_HOST=unix://$DOCKTAP_SOCKET' to route Docker CLI through proxy"
echo "  TruCon internal UDS path: $TRUCON_UDS_PATH"

trap cleanup EXIT INT TERM

ensure_startup_sigstore_token

echo "Starting TC API on $HOST:$PORT"
echo "Debug mode: $DEBUG"

# Start the FastAPI application
if [[ "$START_MODE" == "dev" ]]; then
    echo "Starting in development mode with auto-reload..."
    "$PYTHON_BIN" -m uvicorn tc_api.api.app:app --host $HOST --port $PORT --reload &
else
    echo "Starting in production mode..."
    "$PYTHON_BIN" -m uvicorn tc_api.api.app:app --host $HOST --port $PORT --workers "$TC_API_WORKERS" &
fi

TC_API_PID=$!
echo "$TC_API_PID" > "$TC_API_PID_FILE"

wait "$TC_API_PID"

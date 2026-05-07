#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

OPENCLAW_GATEWAY_CONTAINER="${OPENCLAW_GATEWAY_CONTAINER:-openclaw-gateway}"
OPENCLAW_DOCKER_HOST="${OPENCLAW_DOCKER_HOST:-unix:///var/run/docktap/docker.sock}"
PULL_IMAGE="${PULL_IMAGE:-hello-world:latest}"
LOG_TIMEOUT_SECONDS="${LOG_TIMEOUT_SECONDS:-30}"
LOG_POLL_INTERVAL_SECONDS="${LOG_POLL_INTERVAL_SECONDS:-1}"
DOCKTAP_LOG_FILE="${DOCKTAP_LOG_FILE:-$REPO_ROOT/logs/docktap-latest.log}"
TRUCON_LOG_FILE="${TRUCON_LOG_FILE:-$REPO_ROOT/logs/trucon-latest.log}"

default_python_bin() {
	if [[ -n "${PYTHON_BIN:-}" ]]; then
		echo "$PYTHON_BIN"
	elif [[ -x "$REPO_ROOT/venv/bin/python" ]]; then
		echo "$REPO_ROOT/venv/bin/python"
	else
		echo "python3"
	fi
}

PYTHON_BIN="$(default_python_bin)"

fail() {
	echo "Error: $*" >&2
	exit 1
}

need_cmd() {
	command -v "$1" >/dev/null 2>&1 || fail "required command not found: $1"
}

run_python() {
	PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" "$@"
}

docker_exec_openclaw() {
	local cmd="$1"
	docker exec -e DOCKER_HOST="$OPENCLAW_DOCKER_HOST" "$OPENCLAW_GATEWAY_CONTAINER" sh -lc "$cmd"
}

verify_openclaw_proxy_path() {
	local socket_path
	if [[ "$OPENCLAW_DOCKER_HOST" =~ ^unix://(.+)$ ]]; then
		socket_path="${BASH_REMATCH[1]}"
	else
		fail "OPENCLAW_DOCKER_HOST must use a unix:// socket path; got '${OPENCLAW_DOCKER_HOST}'"
	fi

	if ! docker exec "$OPENCLAW_GATEWAY_CONTAINER" sh -lc "test -S '$socket_path'"; then
		cat >&2 <<EOF
OpenClaw is not currently wired to Docktap.

Expected Docker host inside ${OPENCLAW_GATEWAY_CONTAINER}:
  ${OPENCLAW_DOCKER_HOST}

But the socket does not exist inside the container:
  ${socket_path}

Recreate the OpenClaw gateway container so it can reach Docktap, for example by mounting:
  -v /var/run/docktap:/var/run/docktap

and configuring:
  -e DOCKER_HOST=${OPENCLAW_DOCKER_HOST}
EOF
		exit 1
	fi
}

require_reusable_sigstore_token() {
	run_python - <<'PY'
from tc_api.sigstore_identity import resolve_sigstore_identity_token

resolve_sigstore_identity_token(
    "verify-openclaw-pull",
    require_token=True,
    allow_interactive=False,
)
PY
}

token_seconds_remaining() {
	run_python - <<'PY'
from tc_api.sigstore_identity import _load_cached_token_from_disk, token_seconds_remaining

token = _load_cached_token_from_disk()
remaining = token_seconds_remaining(token) if token else None
print("unknown" if remaining is None else remaining)
PY
}

line_count() {
	local file_path="$1"
	if [[ -f "$file_path" ]]; then
		wc -l < "$file_path"
	else
		echo 0
	fi
}

new_log_text() {
	local file_path="$1"
	local start_line="$2"
	if [[ ! -f "$file_path" ]]; then
		return 0
	fi
	sed -n "$((start_line + 1)),\$p" "$file_path"
}

need_cmd docker
need_cmd sed

docker container inspect "$OPENCLAW_GATEWAY_CONTAINER" >/dev/null 2>&1 || fail "container '${OPENCLAW_GATEWAY_CONTAINER}' is not running"
[[ -f "$DOCKTAP_LOG_FILE" ]] || fail "Docktap log file not found: $DOCKTAP_LOG_FILE"
[[ -f "$TRUCON_LOG_FILE" ]] || fail "TruCon log file not found: $TRUCON_LOG_FILE"

echo "Checking that OpenClaw is wired to Docktap"
verify_openclaw_proxy_path

echo "Checking for a reusable Sigstore identity token"
if ! require_reusable_sigstore_token; then
	cat >&2 <<'EOF'
No reusable Sigstore identity token is available.

Refresh one first, then rerun this script:
  ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
EOF
	exit 1
fi

TOKEN_REMAINING="$(token_seconds_remaining)"
DOCKTAP_START_LINE="$(line_count "$DOCKTAP_LOG_FILE")"
TRUCON_START_LINE="$(line_count "$TRUCON_LOG_FILE")"

echo "OpenClaw pull verification"
echo "  gateway container: ${OPENCLAW_GATEWAY_CONTAINER}"
echo "  docker host:      ${OPENCLAW_DOCKER_HOST}"
echo "  image:            ${PULL_IMAGE}"
echo "  token remaining:  ${TOKEN_REMAINING}s"

echo "[1/3] Pulling ${PULL_IMAGE} through OpenClaw"
docker_exec_openclaw "docker pull ${PULL_IMAGE}"

echo "[2/3] Waiting for Docktap to accept the pull commit"
deadline=$((SECONDS + LOG_TIMEOUT_SECONDS))
record_id=""
while true; do
	new_docktap_lines="$(new_log_text "$DOCKTAP_LOG_FILE" "$DOCKTAP_START_LINE")"
	if printf '%s\n' "$new_docktap_lines" | grep -q 'OPERATION=pull'; then
		record_id="$(printf '%s\n' "$new_docktap_lines" | sed -n 's/.*record_id=\([^,)]*\).*/\1/p' | tail -n1)"
		if [[ -n "$record_id" ]]; then
			break
		fi
	fi
	if (( SECONDS >= deadline )); then
		fail "timed out waiting for Docktap pull commit acceptance; inspect $DOCKTAP_LOG_FILE"
	fi
	sleep "$LOG_POLL_INTERVAL_SECONDS"
done

echo "[3/3] Waiting for TruCon immutable confirmation"
deadline=$((SECONDS + LOG_TIMEOUT_SECONDS))
while true; do
	new_trucon_lines="$(new_log_text "$TRUCON_LOG_FILE" "$TRUCON_START_LINE")"
	if printf '%s\n' "$new_trucon_lines" | grep -q "Record ${record_id} confirmed .*chain_id=default"; then
		break
	fi
	if (( SECONDS >= deadline )); then
		fail "timed out waiting for TruCon confirmation for record_id=${record_id}; inspect $TRUCON_LOG_FILE"
	fi
	sleep "$LOG_POLL_INTERVAL_SECONDS"
done

echo "Pull smoke test succeeded. Relevant new log lines:"
printf '%s\n' "$new_docktap_lines" | grep 'OPERATION=pull\|TruCon commit accepted for pull' || true
printf '%s\n' "$new_trucon_lines" | grep "Record ${record_id} confirmed" || true

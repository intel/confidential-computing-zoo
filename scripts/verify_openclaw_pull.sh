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
VERIFY_CHAIN_ID="${VERIFY_CHAIN_ID:-docktap-runtime}"
VERIFY_JSON="${VERIFY_JSON:-0}"
VERIFY_EVIDENCE_PATH="${VERIFY_EVIDENCE_PATH:-/tmp/docktap-runtime-evidence.json}"
VERIFY_RETRIES="${VERIFY_RETRIES:-4}"
VERIFY_RETRY_DELAY_SECONDS="${VERIFY_RETRY_DELAY_SECONDS:-10}"
TC_API_PID_FILE="${TC_API_PID_FILE:-$REPO_ROOT/logs/pids/tc_api.pid}"

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
TC_VERIFY_BIN="${TC_VERIFY_BIN:-$REPO_ROOT/venv/bin/tc-verify}"
VERIFY_ATTESTED_HEAD_SCRIPT="${VERIFY_ATTESTED_HEAD_SCRIPT:-$REPO_ROOT/scripts/verify_attested_head.py}"

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

run_tc_verify() {
	if [[ -x "$TC_VERIFY_BIN" ]]; then
		PYTHONPATH="$REPO_ROOT/src${PYTHONPATH:+:$PYTHONPATH}" "$TC_VERIFY_BIN" "$@"
	else
		run_python -m tc_api.cli.verify "$@"
	fi
}

run_tc_verify_with_retries() {
	local attempt=1
	local max_attempts="$VERIFY_RETRIES"
	while true; do
		if run_tc_verify "$@"; then
			return 0
		fi
		if (( attempt >= max_attempts )); then
			return 1
		fi
		echo "tc-verify failed on attempt ${attempt}/${max_attempts}; retrying in ${VERIFY_RETRY_DELAY_SECONDS}s to allow Rekor history materialization" >&2
		sleep "$VERIFY_RETRY_DELAY_SECONDS"
		attempt=$((attempt + 1))
		done
}

run_command_with_retries() {
	local attempt=1
	local max_attempts="$VERIFY_RETRIES"
	while true; do
		if "$@"; then
			return 0
		fi
		if (( attempt >= max_attempts )); then
			return 1
		fi
		echo "verification failed on attempt ${attempt}/${max_attempts}; retrying in ${VERIFY_RETRY_DELAY_SECONDS}s to allow Rekor history materialization" >&2
		sleep "$VERIFY_RETRY_DELAY_SECONDS"
		attempt=$((attempt + 1))
	done
}

refresh_sigstore_token_interactively() {
	echo "No reusable Sigstore identity token is available. Starting an interactive refresh..." >&2
	run_python -m tc_api.cli.oidc_verification_code --operation docktap --format none
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

read_tc_api_pid() {
	[[ -f "$TC_API_PID_FILE" ]] || fail "tc_api pid file not found: $TC_API_PID_FILE"
	tr -d '[:space:]' < "$TC_API_PID_FILE"
}

read_active_trucon_service_token() {
	local tc_api_pid
	tc_api_pid="$(read_tc_api_pid)"
	[[ -n "$tc_api_pid" ]] || fail "tc_api pid file is empty: $TC_API_PID_FILE"
	[[ -r "/proc/$tc_api_pid/environ" ]] || fail "cannot read /proc/$tc_api_pid/environ for tc_api process"
	tr '\0' '\n' < "/proc/$tc_api_pid/environ" | sed -n 's/^TRUCON_SERVICE_TOKEN=//p' | tail -n1
}

export_attested_head_evidence() {
	local chain_id="$1"
	local output_path="$2"
	local token="$3"

	TRUCON_SERVICE_TOKEN="$token" VERIFY_CHAIN_ID="$chain_id" VERIFY_EVIDENCE_PATH="$output_path" run_python - <<'PY'
import json
import os
import urllib.request

chain_id = os.environ["VERIFY_CHAIN_ID"]
output_path = os.environ["VERIFY_EVIDENCE_PATH"]
token = os.environ["TRUCON_SERVICE_TOKEN"]
url = f"http://127.0.0.1:8001/evidence/{chain_id}"
request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
with urllib.request.urlopen(request, timeout=30) as response:
    evidence = json.loads(response.read().decode("utf-8"))
with open(output_path, "w", encoding="utf-8") as handle:
    json.dump(evidence, handle, indent=2)
print(output_path)
PY
}

read_head_log_id_from_evidence() {
	local evidence_path="$1"
	VERIFY_EVIDENCE_PATH="$evidence_path" run_python - <<'PY'
import json
import os

with open(os.environ["VERIFY_EVIDENCE_PATH"], "r", encoding="utf-8") as handle:
    evidence = json.load(handle)
print(evidence["head_log_id"])
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
	if [[ ! -t 0 || ! -t 1 ]]; then
		cat >&2 <<'EOF'
No reusable Sigstore identity token is available.

Refresh one first, then rerun this script:
  ./venv/bin/tc-oidc-verification-code --operation docktap --format none

Fallback:
  ./venv/bin/tc-client --base-url http://127.0.0.1:8000 --sigstore-login oob sigstore-token --format json
EOF
		exit 1
	fi

	refresh_sigstore_token_interactively
	require_reusable_sigstore_token
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
	if printf '%s\n' "$new_trucon_lines" | grep -q "Record ${record_id} confirmed .*chain_id=${VERIFY_CHAIN_ID}"; then
		break
	fi
	if (( SECONDS >= deadline )); then
		fail "timed out waiting for TruCon confirmation for record_id=${record_id}; inspect $TRUCON_LOG_FILE"
	fi
	sleep "$LOG_POLL_INTERVAL_SECONDS"
done

echo "[4/4] Exporting attested-head evidence and running tc-verify"
TRUCON_SERVICE_TOKEN="$(read_active_trucon_service_token)"
[[ -n "$TRUCON_SERVICE_TOKEN" ]] || fail "TRUCON_SERVICE_TOKEN was not found in the running tc_api process environment"
export_attested_head_evidence "$VERIFY_CHAIN_ID" "$VERIFY_EVIDENCE_PATH" "$TRUCON_SERVICE_TOKEN" >/dev/null

VERIFY_HEAD_LOG_ID="$(read_head_log_id_from_evidence "$VERIFY_EVIDENCE_PATH")"
[[ -n "$VERIFY_HEAD_LOG_ID" ]] || fail "head_log_id was not present in exported evidence: $VERIFY_EVIDENCE_PATH"

verify_args=("$VERIFY_ATTESTED_HEAD_SCRIPT" --evidence "$VERIFY_EVIDENCE_PATH" --expected-head-log-id "$VERIFY_HEAD_LOG_ID")
if [[ "$VERIFY_JSON" == "1" || "$VERIFY_JSON" == "true" ]]; then
	verify_args+=(--json)
fi
run_command_with_retries run_python "${verify_args[@]}"

echo "Pull smoke test succeeded. Relevant new log lines:"
printf '%s\n' "$new_docktap_lines" | grep 'OPERATION=pull\|TruCon commit accepted for pull' || true
printf '%s\n' "$new_trucon_lines" | grep "Record ${record_id} confirmed" || true
echo "Evidence written to: ${VERIFY_EVIDENCE_PATH}"

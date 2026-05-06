#!/bin/bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TRUST_SERVICE_IMAGE="${TRUST_SERVICE_IMAGE:-tc-api-trust-service:dev}"
TRUST_SERVICE_CONTAINER_NAME="${TRUST_SERVICE_CONTAINER_NAME:-tc-api-trust-service}"
TRUST_SERVICE_BUILD="${TRUST_SERVICE_BUILD:-missing}"
TRUST_SERVICE_HOST="${TRUST_SERVICE_HOST:-127.0.0.1}"
TRUST_SERVICE_PORT="${TRUST_SERVICE_PORT:-8006}"
KBS_HOST="${KBS_HOST:-127.0.0.1}"
KBS_PORT="${KBS_PORT:-8080}"

wait_for_tcp_port() {
	local host="$1"
	local port="$2"
	local service_name="$3"
	local timeout_seconds="${4:-60}"
	local start_ts

	start_ts=$(date +%s)
	while true; do
		if bash -lc "exec 3<>/dev/tcp/${host}/${port}" >/dev/null 2>&1; then
			echo "✓ ${service_name} is listening on ${host}:${port}"
			return 0
		fi

		if [ $(( $(date +%s) - start_ts )) -ge "$timeout_seconds" ]; then
			echo "Timed out waiting for ${service_name} on ${host}:${port}" >&2
			return 1
		fi

		sleep 1
	done
}

docker_container_exists() {
	docker container inspect "$1" >/dev/null 2>&1
}

docker_image_exists() {
	docker image inspect "$1" >/dev/null 2>&1
}

cleanup() {
	local exit_code=$?

	if [ -n "${main_pid:-}" ] && kill -0 "$main_pid" >/dev/null 2>&1; then
		kill -TERM "$main_pid" 2>/dev/null || true
		wait "$main_pid" 2>/dev/null || true
	fi

	if docker_container_exists "$TRUST_SERVICE_CONTAINER_NAME"; then
		docker rm -f "$TRUST_SERVICE_CONTAINER_NAME" >/dev/null 2>&1 || true
	fi

	exit "$exit_code"
}
trap cleanup EXIT INT TERM

if ! command -v docker >/dev/null 2>&1; then
	echo "Error: docker is required" >&2
	exit 1
fi

wait_for_tcp_port "$KBS_HOST" "$KBS_PORT" "KBS" "${KBS_READY_TIMEOUT_SECONDS:-60}"

case "$TRUST_SERVICE_BUILD" in
	always)
		echo "Building trust-service image ${TRUST_SERVICE_IMAGE}"
		docker build -f "$REPO_ROOT/aa_asr_cdh/Dockerfile" -t "$TRUST_SERVICE_IMAGE" "$REPO_ROOT/aa_asr_cdh"
		;;
	missing)
		if ! docker_image_exists "$TRUST_SERVICE_IMAGE"; then
			echo "Building trust-service image ${TRUST_SERVICE_IMAGE}"
			docker build -f "$REPO_ROOT/aa_asr_cdh/Dockerfile" -t "$TRUST_SERVICE_IMAGE" "$REPO_ROOT/aa_asr_cdh"
		fi
		;;
	never)
		if ! docker_image_exists "$TRUST_SERVICE_IMAGE"; then
			echo "Error: trust-service image ${TRUST_SERVICE_IMAGE} is missing and TRUST_SERVICE_BUILD=never" >&2
			exit 1
		fi
		;;
	*)
		echo "Error: unsupported TRUST_SERVICE_BUILD value: ${TRUST_SERVICE_BUILD}" >&2
		exit 1
		;;
esac

if docker_container_exists "$TRUST_SERVICE_CONTAINER_NAME"; then
	docker rm -f "$TRUST_SERVICE_CONTAINER_NAME" >/dev/null
fi

docker_args=(
	--detach
	--name "$TRUST_SERVICE_CONTAINER_NAME"
	--network host
	--privileged
	-v /var/run/docker.sock:/var/run/docker.sock
	-v /etc/hosts:/etc/hosts
	-v /sys/kernel/config:/sys/kernel/config
	-e KBS_READY_TIMEOUT_SECONDS="${KBS_READY_TIMEOUT_SECONDS:-60}"
	-e AA_READY_TIMEOUT_SECONDS="${AA_READY_TIMEOUT_SECONDS:-60}"
	-e CDH_READY_TIMEOUT_SECONDS="${CDH_READY_TIMEOUT_SECONDS:-60}"
)

if [ -e /dev/tdx_guest ]; then
	docker_args+=( -v /dev/tdx_guest:/dev/tdx_guest )
fi

if [ -f /etc/tdx-attest.conf ]; then
	docker_args+=( -v /etc/tdx-attest.conf:/etc/tdx-attest.conf )
fi

if [ -f /etc/sgx_default_qcnl.conf ]; then
	docker_args+=( -v /etc/sgx_default_qcnl.conf:/etc/sgx_default_qcnl.conf )
fi

echo "Starting trust-service container ${TRUST_SERVICE_CONTAINER_NAME}"
docker run "${docker_args[@]}" "$TRUST_SERVICE_IMAGE" >/dev/null

if ! wait_for_tcp_port "$TRUST_SERVICE_HOST" "$TRUST_SERVICE_PORT" "api-server-rest" "${TRUST_SERVICE_READY_TIMEOUT_SECONDS:-90}"; then
	echo "Recent trust-service logs:" >&2
	docker logs --tail 50 "$TRUST_SERVICE_CONTAINER_NAME" >&2 || true
	exit 1
fi

echo "Starting tc-api stack via start.sh"
cd "$REPO_ROOT"
./start.sh "$@" &
main_pid=$!
wait "$main_pid"

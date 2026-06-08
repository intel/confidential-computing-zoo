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

set -euo pipefail

export no_proxy="localhost,127.0.0.1,192.168.0.0/16,10.0.0.0/8,172.16.0.0/12,.local"

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

wait_for_unix_socket() {
    local socket_path="$1"
    local service_name="$2"
    local timeout_seconds="${3:-60}"
    local start_ts

    start_ts=$(date +%s)
    while true; do
        if [ -S "$socket_path" ]; then
            echo "✓ ${service_name} socket is ready at ${socket_path}"
            return 0
        fi

        if [ $(( $(date +%s) - start_ts )) -ge "$timeout_seconds" ]; then
            echo "Timed out waiting for ${service_name} socket at ${socket_path}" >&2
            return 1
        fi

        sleep 1
    done
}

mask_host_ccel() {
    if [ "${MASK_HOST_CCEL:-1}" = "0" ]; then
        echo "Skipping host CCEL masking"
        return 0
    fi

    if [ ! -e /sys/firmware/acpi/tables/CCEL ] && [ ! -e /sys/firmware/acpi/tables/data/CCEL ]; then
        echo "Host CCEL not visible in container"
        return 0
    fi

    echo "Masking host CCEL paths to avoid guest attester/verifier mismatch"
    mount -t tmpfs tmpfs /sys/firmware/acpi/tables
    mkdir -p /sys/firmware/acpi/tables/data

    if [ -e /sys/firmware/acpi/tables/CCEL ] || [ -e /sys/firmware/acpi/tables/data/CCEL ]; then
        echo "Failed to mask host CCEL paths" >&2
        return 1
    fi
}

cleanup() {
    if [ -n "${cdh_pid:-}" ]; then
        kill -TERM "$cdh_pid" 2>/dev/null || true
    fi
    if [ -n "${aa_pid:-}" ]; then
        kill -TERM "$aa_pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT INT TERM

mkdir -p /run/confidential-containers/attestation-agent
rm -f /run/confidential-containers/attestation-agent/attestation-agent.sock
rm -f /run/confidential-containers/cdh.sock

mask_host_ccel

wait_for_tcp_port 127.0.0.1 8080 "KBS" "${KBS_READY_TIMEOUT_SECONDS:-60}"

echo "Start attestation-agent"
RUST_LOG=debug attestation-agent -c /app/aa.toml &
aa_pid=$!
wait_for_unix_socket "/run/confidential-containers/attestation-agent/attestation-agent.sock" "attestation-agent" "${AA_READY_TIMEOUT_SECONDS:-60}"

echo "Start confidential-data-hub"
RUST_LOG=debug confidential-data-hub -c /app/cdh.toml &
cdh_pid=$!
wait_for_unix_socket "/run/confidential-containers/cdh.sock" "confidential-data-hub" "${CDH_READY_TIMEOUT_SECONDS:-60}"

echo "Start api-server-rest"
exec api-server-rest

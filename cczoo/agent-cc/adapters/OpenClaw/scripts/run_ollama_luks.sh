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

LUKS_MOUNT_ROOT="${OLLAMA_LUKS_MOUNT_ROOT:-/home/encrypted_storage}"
LUKS_SUBDIR="${OLLAMA_LUKS_SUBDIR:-ollama}"
OLLAMA_MODELS="${OLLAMA_MODELS:-${LUKS_MOUNT_ROOT}/${LUKS_SUBDIR}}"

fail() {
    echo "[ollama-luks] ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

require_luks_mount() {
    local canonical_models
    local canonical_root

    require_command mountpoint
    require_command realpath
    mountpoint -q "$LUKS_MOUNT_ROOT" || {
        fail "LUKS mount is not active: $LUKS_MOUNT_ROOT"
    }

    canonical_root="$(realpath -e "$LUKS_MOUNT_ROOT")" || \
        fail "Unable to resolve LUKS mount: $LUKS_MOUNT_ROOT"
    canonical_models="$(realpath -m "$OLLAMA_MODELS")" || \
        fail "Unable to resolve model directory: $OLLAMA_MODELS"
    case "$canonical_models" in
        "$canonical_root"/*) ;;
        *) fail "OLLAMA_MODELS must be inside LUKS mount: $canonical_root" ;;
    esac

    LUKS_MOUNT_ROOT="$canonical_root"
    OLLAMA_MODELS="$canonical_models"
}

main() {
    require_command ollama
    require_luks_mount

    mkdir -p "$OLLAMA_MODELS"
    chmod 700 "$OLLAMA_MODELS"

    export OLLAMA_MODELS
    echo "[ollama-luks] model directory: $OLLAMA_MODELS"

    case "${1:-serve}" in
        serve)
            shift
            exec ollama serve "$@"
            ;;
        pull)
            [[ $# -eq 2 ]] || fail "Usage: $0 pull MODEL"
            exec ollama pull "$2"
            ;;
        *)
            fail "Usage: $0 [serve | pull MODEL]"
            ;;
    esac
}

main "$@"
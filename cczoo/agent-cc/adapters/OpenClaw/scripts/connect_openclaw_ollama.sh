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

OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
OLLAMA_CONTAINER_BASE_URL="${OLLAMA_CONTAINER_BASE_URL:-http://host.docker.internal:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2}"
OLLAMA_API_KEY="${OLLAMA_API_KEY:-ollama-local}"
OLLAMA_CONTEXT_WINDOW="${OLLAMA_CONTEXT_WINDOW:-32768}"
OLLAMA_MAX_TOKENS="${OLLAMA_MAX_TOKENS:-4096}"
OPENCLAW_CONTAINER="${OPENCLAW_CONTAINER:-agentcc-openclaw-sbx-gateway}"
WAIT_ATTEMPTS="${WAIT_ATTEMPTS:-60}"
WAIT_INTERVAL="${WAIT_INTERVAL:-2}"

log() {
    printf '[ollama-provider] %s\n' "$*"
}

fail() {
    echo "[ollama-provider] ERROR: $*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || fail "Missing required command: $1"
}

wait_for_ollama() {
    local attempt

    for ((attempt=1; attempt<=WAIT_ATTEMPTS; attempt++)); do
        if curl -fsS "${OLLAMA_BASE_URL%/}/api/tags" >/dev/null 2>&1; then
            log "Ollama is ready: ${OLLAMA_BASE_URL}"
            return 0
        fi
        sleep "$WAIT_INTERVAL"
    done

    fail "Ollama did not become ready: ${OLLAMA_BASE_URL}"
}

check_container_access() {
        docker exec "$OPENCLAW_CONTAINER" node -e '
const baseUrl = process.argv[1].replace(/\/$/, "");
fetch(`${baseUrl}/api/tags`)
    .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
    })
    .catch((error) => {
        console.error(error.message);
        process.exit(1);
    });
' "$OLLAMA_CONTAINER_BASE_URL" >/dev/null 2>&1 || \
                fail "OpenClaw container cannot reach Ollama at ${OLLAMA_CONTAINER_BASE_URL}. On Linux, add host.docker.internal:host-gateway to the container or set OLLAMA_CONTAINER_BASE_URL to a reachable address."
}

ensure_model() {
    local models

    models="$(curl -fsS "${OLLAMA_BASE_URL%/}/api/tags")" || \
        fail "Unable to list Ollama models"
    if ! MODEL_LIST="$models" EXPECTED_MODEL="$OLLAMA_MODEL" python3 - <<'PY'
import json
import os
import sys

try:
    names = [item.get("name", "") for item in json.loads(os.environ["MODEL_LIST"]).get("models", [])]
except (KeyError, TypeError, ValueError):
    sys.exit("Ollama returned an invalid /api/tags response")

expected = os.environ["EXPECTED_MODEL"]
if not any(name == expected or name.startswith(expected + ":") for name in names):
    sys.exit(f"Ollama model is not installed: {expected}; installed models: {', '.join(names) or '<none>'}")
PY
    then
        fail "Install the model first with: ollama pull ${OLLAMA_MODEL}"
    fi
}

set_config() {
    if [[ "${3:-}" == "--strict-json" ]]; then
        docker exec "$OPENCLAW_CONTAINER" node /app/dist/index.js config set \
            "$1" "$2" --strict-json >/dev/null
    else
        docker exec "$OPENCLAW_CONTAINER" node /app/dist/index.js config set \
            "$1" "$2" >/dev/null
    fi
}

main() {
    require_command curl
    require_command docker
    require_command python3

    [[ -n "$OLLAMA_MODEL" ]] || fail "OLLAMA_MODEL must not be empty"
    [[ "$OLLAMA_BASE_URL" =~ ^https?:// ]] || fail "OLLAMA_BASE_URL must be an HTTP(S) URL"
    [[ "$OLLAMA_CONTAINER_BASE_URL" =~ ^https?:// ]] || \
        fail "OLLAMA_CONTAINER_BASE_URL must be an HTTP(S) URL"
    [[ "$OLLAMA_MODEL" =~ ^[A-Za-z0-9._:/-]+$ ]] || \
        fail "OLLAMA_MODEL contains unsupported characters: $OLLAMA_MODEL"
    [[ "$OLLAMA_CONTEXT_WINDOW" =~ ^[0-9]+$ ]] || fail "OLLAMA_CONTEXT_WINDOW must be an integer"
    [[ "$OLLAMA_MAX_TOKENS" =~ ^[0-9]+$ ]] || fail "OLLAMA_MAX_TOKENS must be an integer"

    docker inspect "$OPENCLAW_CONTAINER" >/dev/null 2>&1 || \
        fail "OpenClaw container not found: $OPENCLAW_CONTAINER"

    wait_for_ollama
    ensure_model
    check_container_access

    log "Configuring Ollama provider: ${OLLAMA_MODEL}"
    set_config "models.providers.ollama.baseUrl" "${OLLAMA_CONTAINER_BASE_URL%/}/v1"
    set_config "models.providers.ollama.apiKey" "$OLLAMA_API_KEY"
    set_config "models.providers.ollama.api" "openai-completions"
    set_config "models.providers.ollama.models" \
        "[{\"id\":\"${OLLAMA_MODEL}\",\"name\":\"${OLLAMA_MODEL}\",\"contextWindow\":${OLLAMA_CONTEXT_WINDOW},\"maxTokens\":${OLLAMA_MAX_TOKENS}}]" \
        "--strict-json"
    set_config "agents.defaults.model.primary" "ollama/${OLLAMA_MODEL}"

    log "Restarting OpenClaw gateway"
    docker restart "$OPENCLAW_CONTAINER" >/dev/null
    log "Ollama is configured as the OpenClaw primary model"
    log "Provider endpoint: ${OLLAMA_CONTAINER_BASE_URL%/}/v1"
    log "Primary model: ollama/${OLLAMA_MODEL}"
}

main "$@"
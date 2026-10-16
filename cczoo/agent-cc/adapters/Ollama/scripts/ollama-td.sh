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

DROP_IN_DIR="/etc/systemd/system/ollama.service.d"
DROP_IN_FILE="${DROP_IN_DIR}/override.conf"
DEFAULT_MODEL="qwen2.5:7b"

usage() {
  cat <<'EOF'
Usage:
  ollama-td.sh setup [local|docker|HOST:PORT] [MODEL]
  ollama-td.sh configure [local|docker|HOST:PORT]
  ollama-td.sh pull [MODEL]
  ollama-td.sh start|stop
  ollama-td.sh status|test|endpoint [local|docker|HOST:PORT]

local binds Ollama to 127.0.0.1:11434. docker binds it to the docker0 IPv4
address. A custom HOST:PORT can be supplied for a non-default Docker network.
EOF
}

as_root() {
  if [[ "$EUID" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

resolve_bind_address() {
  local scope="${1:-local}"
  local address

  case "$scope" in
    local)
      address="127.0.0.1:11434"
      ;;
    docker)
      command -v ip >/dev/null 2>&1 || {
        echo "ERROR: 'ip' is required to detect the docker0 address." >&2
        return 1
      }
      address="$(ip -4 -o addr show dev docker0 2>/dev/null | awk 'NR == 1 { sub(/\/.*/, "", $4); print $4 }')"
      [[ -n "$address" ]] || {
        echo "ERROR: docker0 has no IPv4 address; use a custom HOST:PORT instead." >&2
        return 1
      }
      address="${address}:11434"
      ;;
    *)
      address="$scope"
      ;;
  esac

  [[ "$address" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}:[0-9]{1,5}$ ]] || {
    echo "ERROR: expected local, docker, or an IPv4 HOST:PORT address." >&2
    return 1
  }
  [[ "$address" != 0.0.0.0:* ]] || {
    echo "ERROR: binding Ollama to 0.0.0.0 is not allowed by this script." >&2
    return 1
  }

  printf '%s\n' "$address"
}

configure_service() {
  local address="$1"

  as_root install -d "$DROP_IN_DIR"
  printf '[Service]\nEnvironment="OLLAMA_HOST=%s"\n' "$address" \
    | as_root tee "$DROP_IN_FILE" >/dev/null
  as_root systemctl daemon-reload
  as_root systemctl enable --now ollama
}

base_url_for() {
  local address
  address="$(resolve_bind_address "${1:-local}")" || return 1
  printf 'http://%s\n' "${address%:*}:${address##*:}"
}

ACTION="${1:-}"
[[ -n "$ACTION" ]] || { usage >&2; exit 2; }

case "$ACTION" in
  setup)
    SCOPE="${2:-local}"
    MODEL="${3:-$DEFAULT_MODEL}"
    BIND_ADDRESS="$(resolve_bind_address "$SCOPE")"
    command -v curl >/dev/null 2>&1 || {
      echo "ERROR: curl is required to install Ollama." >&2
      exit 1
    }
    curl -fsSL https://ollama.com/install.sh | sh
    configure_service "$BIND_ADDRESS"
    ollama pull "$MODEL"
    ;;
  configure)
    BIND_ADDRESS="$(resolve_bind_address "${2:-local}")"
    configure_service "$BIND_ADDRESS"
    ;;
  pull)
    command -v ollama >/dev/null 2>&1 || {
      echo "ERROR: Ollama is not installed." >&2
      exit 1
    }
    ollama pull "${2:-$DEFAULT_MODEL}"
    ;;
  start|stop)
    as_root systemctl "$ACTION" ollama
    ;;
  status)
    as_root systemctl status ollama --no-pager
    BASE_URL="$(base_url_for "${2:-local}")"
    curl -fsS "${BASE_URL}/api/tags"
    printf '\n'
    ;;
  test)
    BASE_URL="$(base_url_for "${2:-local}")"
    curl -fsS "${BASE_URL}/api/tags" >/dev/null
    curl -fsS "${BASE_URL}/v1/models"
    printf '\nOllama API is reachable at %s/v1\n' "$BASE_URL"
    ;;
  endpoint)
    BASE_URL="$(base_url_for "${2:-local}")"
    printf 'OLLAMA_BASE_URL=%s\nOPENAI_COMPATIBLE_BASE_URL=%s/v1\n' \
      "$BASE_URL" "$BASE_URL"
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "ERROR: unknown command '$ACTION'." >&2
    usage >&2
    exit 2
    ;;
esac
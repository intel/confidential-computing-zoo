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

"""Centralized configuration for the Docktap sidecar.

Collects all ``DOCKTAP_*`` environment variable reads into one place
so the env-var surface is discoverable and defaults cannot diverge.
"""

import os
from typing import List


VALID_AUTH_MODES = {"explicit_delegation", "delegation_disabled"}
DEFAULT_DELEGATION_SCOPE = ["pull", "create", "start", "stop", "rm"]


def auth_mode() -> str:
    raw_value = os.environ.get("DOCKTAP_AUTH_MODE", "explicit_delegation").strip().lower()
    if raw_value in VALID_AUTH_MODES:
        return raw_value
    return "explicit_delegation"


def delegation_required() -> bool:
    return auth_mode() == "explicit_delegation"


def delegation_enabled() -> bool:
    return auth_mode() != "delegation_disabled"


def delegation_scope() -> List[str]:
    raw_value = os.environ.get("DOCKTAP_DELEGATION_SCOPE", ",".join(DEFAULT_DELEGATION_SCOPE)).strip()
    if not raw_value:
        return list(DEFAULT_DELEGATION_SCOPE)

    resolved = [value.strip().lower() for value in raw_value.split(",") if value.strip()]
    if not resolved:
        return list(DEFAULT_DELEGATION_SCOPE)

    allowed = set(DEFAULT_DELEGATION_SCOPE)
    if any(value not in allowed for value in resolved):
        return list(DEFAULT_DELEGATION_SCOPE)
    return resolved


def require_attestation() -> bool:
    return os.environ.get("DOCKTAP_REQUIRE_ATTESTATION", "1") == "1"

# ---------------------------------------------------------------------------
# TruCon connectivity
# ---------------------------------------------------------------------------
TRUCON_URL: str = os.environ.get("TRUCON_URL", "http://127.0.0.1:8001")
RUNTIME_CHAIN_ID: str = "default"

# ---------------------------------------------------------------------------
# Retry / queue tuning
# ---------------------------------------------------------------------------
TRUCON_MAX_RETRY_ATTEMPTS: int = int(os.environ.get("DOCKTAP_TRUCON_MAX_RETRY_ATTEMPTS", "3"))
TRUCON_RETRY_BASE_DELAY: float = float(os.environ.get("DOCKTAP_TRUCON_RETRY_BASE_DELAY", "1.0"))
TRUCON_RETRY_MAX_DELAY: float = float(os.environ.get("DOCKTAP_TRUCON_RETRY_MAX_DELAY", "30.0"))
ACKED_RETRY_RETENTION_HOURS: float = float(os.environ.get("DOCKTAP_ACKED_RETRY_RETENTION_HOURS", "24"))
TERMINAL_RETRY_RETENTION_HOURS: float = float(os.environ.get("DOCKTAP_TERMINAL_RETRY_RETENTION_HOURS", "168"))

# ---------------------------------------------------------------------------
# Workload store
# ---------------------------------------------------------------------------
WORKLOAD_DB: str = os.environ.get("DOCKTAP_WORKLOAD_DB", "/dev/shm/docktap/container_map.db")

# ---------------------------------------------------------------------------
# GC intervals
# ---------------------------------------------------------------------------
GC_INTERVAL_SECONDS: float = float(os.environ.get("DOCKTAP_GC_INTERVAL_SECONDS", "300"))
OPERATION_RETENTION_HOURS: float = float(os.environ.get("DOCKTAP_OPERATION_RETENTION_HOURS", "24"))
REMOVED_CONTAINER_RETENTION_HOURS: float = float(os.environ.get("DOCKTAP_REMOVED_CONTAINER_RETENTION_HOURS", "24"))

# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------
DELEGATION_TTL_SECONDS: int = int(os.environ.get("DOCKTAP_DELEGATION_TTL_SECONDS", "14400"))

# ---------------------------------------------------------------------------
# Health / networking
# ---------------------------------------------------------------------------
HEALTH_PORT: int = int(os.environ.get("DOCKTAP_HEALTH_PORT", "8002"))
SOCK_BRIDGE_SOCKET: str = os.environ.get("SOCK_BRIDGE_SOCKET", "/tmp/docker-proxy.sock")
DOCKER_SOCKET: str = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")

# ---------------------------------------------------------------------------
# Proxy / attestation
# ---------------------------------------------------------------------------
ATTESTATION_API_URL: str = os.environ.get("DOCKTAP_ATTESTATION_API_URL", "http://127.0.0.1:8000")
ATTESTATION_BROWSER_BASE_URL: str = os.environ.get(
    "DOCKTAP_ATTESTATION_BROWSER_BASE_URL",
    os.environ.get("DOCKTAP_ATTESTATION_API_URL", "http://127.0.0.1:8000"),
)

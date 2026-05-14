"""Centralized configuration for the Docktap sidecar.

Collects all ``DOCKTAP_*`` environment variable reads into one place
so the env-var surface is discoverable and defaults cannot diverge.
"""

import os

# ---------------------------------------------------------------------------
# TruCon connectivity
# ---------------------------------------------------------------------------
TRUCON_URL: str = os.environ.get("TRUCON_URL", "http://127.0.0.1:8001")
RUNTIME_CHAIN_ID: str = os.environ.get("DOCKTAP_RUNTIME_CHAIN_ID", "docktap-runtime")

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
REQUIRE_ATTESTATION: bool = os.environ.get("DOCKTAP_REQUIRE_ATTESTATION", "1") == "1"
LIFECYCLE_GRANT_TTL_SECONDS: str = os.environ.get("DOCKTAP_LIFECYCLE_GRANT_TTL_SECONDS", "").strip()
ATTESTATION_API_URL: str = os.environ.get("DOCKTAP_ATTESTATION_API_URL", "http://127.0.0.1:8000")
ATTESTATION_BROWSER_BASE_URL: str = os.environ.get(
    "DOCKTAP_ATTESTATION_BROWSER_BASE_URL",
    os.environ.get("DOCKTAP_ATTESTATION_API_URL", "http://127.0.0.1:8000"),
)

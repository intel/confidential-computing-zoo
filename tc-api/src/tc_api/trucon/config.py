"""Centralized configuration for the TruCon sequencer.

Mirrors the pattern in ``tc_api.config`` — all environment variable reads
are collected here so the surface is discoverable in a single place.
"""

import os

# ---------------------------------------------------------------------------
# Sequencer tuning
# ---------------------------------------------------------------------------
INTENT_TTL_SECONDS: int = int(os.environ.get("TRUCON_INTENT_TTL_SECONDS", "300"))
RTMR_INDEX: int = int(os.environ.get("TRUCON_RTMR_INDEX", "2"))
QUEUE_SNAPSHOT_HEARTBEAT_TICKS: int = max(
    1, int(os.environ.get("TRUCON_QUEUE_SNAPSHOT_HEARTBEAT_TICKS", "12"))
)

# ---------------------------------------------------------------------------
# Immutable backend selection
# ---------------------------------------------------------------------------
TC_IMMUTABLE_BACKEND: str = os.environ.get("TC_IMMUTABLE_BACKEND", "rekor").strip().lower()

# ---------------------------------------------------------------------------
# Bundle mirror (optional)
# ---------------------------------------------------------------------------
BUNDLE_MIRROR_LOCATION: str = (
    os.environ.get("TRUCON_BUNDLE_MIRROR")
    or os.environ.get("TRUCON_BUNDLE_MIRROR_URL")
    or os.environ.get("TRUCON_BUNDLE_MIRROR_DIR")
    or ""
)

# ---------------------------------------------------------------------------
# Service authentication & networking
# ---------------------------------------------------------------------------
AUTH_DISABLED: bool = os.environ.get("TRUCON_AUTH_DISABLED", "").lower() == "true"
SERVICE_TOKEN: str = os.environ.get("TRUCON_SERVICE_TOKEN", "")
TRUCON_UDS_PATH: str = os.environ.get("TRUCON_UDS_PATH", "")
TRUCON_HTTP_PORT: int = int(os.environ.get("TRUCON_PORT", "8001"))

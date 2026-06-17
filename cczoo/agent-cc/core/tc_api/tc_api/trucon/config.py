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

"""Centralized configuration for the TruCon sequencer.

Mirrors the pattern in ``tc_api.config`` — all environment variable reads
are collected here so the surface is discoverable in a single place.

Phase-one immutable backend semantics:
- ``TC_IMMUTABLE_WRITE_BACKENDS`` defines the ordered write set.
- ``TC_IMMUTABLE_PRIMARY_BACKEND`` defines the authoritative read/confirm backend.
- ``TC_IMMUTABLE_WRITE_POLICY=primary`` keeps confirmation anchored to the
    primary backend while secondary outcomes remain observable for future rollout.

``TC_IMMUTABLE_BACKEND`` remains as a compatibility alias for single-backend
deployments when ``TC_IMMUTABLE_WRITE_BACKENDS`` is unset.
"""

import os
from dataclasses import dataclass
from typing import Tuple

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
SUPPORTED_IMMUTABLE_BACKENDS: Tuple[str, ...] = ("rekor", "onchain")
SUPPORTED_IMMUTABLE_WRITE_POLICIES: Tuple[str, ...] = ("primary",)


@dataclass(frozen=True)
class ImmutableBackendConfig:
    write_backends: Tuple[str, ...]
    primary_backend: str
    write_policy: str


def _split_backend_values(raw_value: str) -> Tuple[str, ...]:
    values = []
    seen = set()
    for item in raw_value.split(","):
        backend = item.strip().lower()
        if not backend or backend in seen:
            continue
        values.append(backend)
        seen.add(backend)
    return tuple(values)


def get_immutable_backend_config() -> ImmutableBackendConfig:
    legacy_backend = os.environ.get("TC_IMMUTABLE_BACKEND", "rekor").strip().lower()
    raw_write_backends = os.environ.get("TC_IMMUTABLE_WRITE_BACKENDS", legacy_backend)
    write_backends = _split_backend_values(raw_write_backends)
    if not write_backends:
        write_backends = ("rekor",)

    unsupported = [backend for backend in write_backends if backend not in SUPPORTED_IMMUTABLE_BACKENDS]
    if unsupported:
        supported = ", ".join(SUPPORTED_IMMUTABLE_BACKENDS)
        raise ValueError(
            f"Unknown immutable backend(s): {', '.join(unsupported)}. Supported: {supported}"
        )

    primary_backend = os.environ.get("TC_IMMUTABLE_PRIMARY_BACKEND", "").strip().lower()
    if not primary_backend:
        primary_backend = write_backends[0] if len(write_backends) == 1 else "rekor"

    if primary_backend not in SUPPORTED_IMMUTABLE_BACKENDS:
        supported = ", ".join(SUPPORTED_IMMUTABLE_BACKENDS)
        raise ValueError(
            f"Unknown primary immutable backend: {primary_backend!r}. Supported: {supported}"
        )

    if primary_backend not in write_backends:
        configured = ", ".join(write_backends)
        raise ValueError(
            f"Primary immutable backend {primary_backend!r} must be included in write backends: {configured}"
        )

    write_policy = os.environ.get("TC_IMMUTABLE_WRITE_POLICY", "primary").strip().lower() or "primary"
    if write_policy not in SUPPORTED_IMMUTABLE_WRITE_POLICIES:
        supported = ", ".join(SUPPORTED_IMMUTABLE_WRITE_POLICIES)
        raise ValueError(
            f"Unsupported immutable write policy: {write_policy!r}. Supported: {supported}"
        )

    if len(write_backends) > 1 and "onchain" in write_backends:
        raise ValueError(
            "Unsupported immutable backend fanout configuration 'rekor,onchain': "
            "on-chain fanout remains disabled until the on-chain adapter is implemented"
        )

    return ImmutableBackendConfig(
        write_backends=write_backends,
        primary_backend=primary_backend,
        write_policy=write_policy,
    )


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

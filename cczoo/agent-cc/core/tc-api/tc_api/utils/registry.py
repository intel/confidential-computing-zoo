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

"""Image registry reference helpers."""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from ..config import ALLOWED_EXTERNAL_IMAGE_REGISTRIES, BUILD_DIR, DOCKER_REGISTRY, DOCKER_REPOSITORY


_TRANSPORT_RE = re.compile(r"^(?P<transport>[a-z][a-z0-9+.-]*):")
_BLOCKED_EXTERNAL_TRANSPORTS = {
    "containers-storage",
    "dir",
    "docker-archive",
    "docker-daemon",
    "oci-archive",
}


def _allowed_external_registries() -> set[str]:
    configured = {
        entry.strip()
        for entry in ALLOWED_EXTERNAL_IMAGE_REGISTRIES.split(",")
        if entry.strip()
    }
    configured.add(DOCKER_REGISTRY)
    return configured


def _validate_oci_layout_path(path_value: str, field_name: str) -> str:
    path = Path(path_value)
    candidate = path if path.is_absolute() else (Path.cwd() / path)
    resolved_path = candidate.resolve(strict=False)
    resolved_base = Path(BUILD_DIR).resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_base)
    except ValueError as exc:
        raise ValueError(f"{field_name} local OCI paths must stay under {resolved_base}") from exc
    return path_value


def _infer_registry_host(image_ref: str) -> str:
    first_segment = image_ref.split("/", 1)[0]
    if "." in first_segment or ":" in first_segment or first_segment == "localhost":
        return first_segment
    return DOCKER_REGISTRY


def validate_external_image_reference(image_ref: str, field_name: str = "image_url") -> str:
    if not image_ref:
        return image_ref

    if os.path.isdir(image_ref):
        return _validate_oci_layout_path(image_ref, field_name)

    transport_match = _TRANSPORT_RE.match(image_ref)
    if transport_match:
        transport = transport_match.group("transport")
        if transport in _BLOCKED_EXTERNAL_TRANSPORTS:
            raise ValueError(f"{field_name} transport '{transport}' is not allowed")
        if transport == "oci":
            return _validate_oci_layout_path(image_ref[len("oci:"):], field_name)
        if transport != "docker":
            raise ValueError(f"{field_name} transport '{transport}' is not supported")
        host = urlsplit(image_ref).netloc
    else:
        host = _infer_registry_host(image_ref)

    if host not in _allowed_external_registries():
        raise ValueError(f"{field_name} registry '{host}' is not allowed")
    return image_ref


def canonical_registry_ref(image_name: str) -> str:
    """Build the canonical registry reference for *image_name*.

    The format mirrors what ``cosign sign`` / ``cosign attest`` / launch
    verification all expect::

        <DOCKER_REGISTRY>/<DOCKER_REPOSITORY>/<base>:latest-encrypted

    For local registries (``localhost:`` / ``127.0.0.1:``), the top-level
    ``DOCKER_REGISTRY`` is omitted because ``DOCKER_REPOSITORY`` already
    includes the host.
    """
    base_name = image_name.split("/")[-1] + ":latest-encrypted"
    if DOCKER_REPOSITORY.startswith(("localhost:", "127.0.0.1:")):
        return f"{DOCKER_REPOSITORY}/{base_name}"
    return f"{DOCKER_REGISTRY}/{DOCKER_REPOSITORY}/{base_name}"

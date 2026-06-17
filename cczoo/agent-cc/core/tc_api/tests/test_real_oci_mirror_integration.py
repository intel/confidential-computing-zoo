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

import hashlib
import json
import os
import time
from typing import Dict
from unittest.mock import Mock

import docker
import pytest

from tlog.backends.rekor.oci_mirror import OciBundleMirror, build_mirror_annotations


ENV_RUN = "TC_API_RUN_REAL_OCI_MIRROR_TESTS"
ENV_IMAGE = "TC_API_REAL_OCI_REGISTRY_IMAGE"
ENV_REPOSITORY = "TC_API_REAL_OCI_MIRROR_REPOSITORY"


def _require_real_oci_env() -> Dict[str, str]:
    if os.getenv(ENV_RUN, "").lower() not in {"1", "true", "yes"}:
        pytest.skip(f"Set {ENV_RUN}=1 to enable the real OCI mirror smoke test")

    return {
        "image": os.getenv(ENV_IMAGE, "registry:2"),
        "repository": os.getenv(ENV_REPOSITORY, "tc-api/oci-bundle-mirror-smoke"),
    }


def _ensure_registry_image(client: docker.DockerClient, image: str) -> None:
    try:
        client.images.get(image)
        return
    except docker.errors.ImageNotFound:
        pass

    try:
        client.images.pull(image)
    except docker.errors.DockerException as exc:
        pytest.skip(
            f"Real OCI mirror smoke test requires Docker image {image!r}, but it was not available locally and pull failed: {exc}. "
            f"Pre-pull/tag the image locally or set {ENV_IMAGE} to a reachable local registry image."
        )


@pytest.fixture(scope="module")
def real_oci_registry_runtime():
    runtime = _require_real_oci_env()
    client = docker.from_env()
    client.ping()
    _ensure_registry_image(client, runtime["image"])

    container = client.containers.run(
        runtime["image"],
        detach=True,
        ports={"5000/tcp": ("127.0.0.1", None)},
        environment={"REGISTRY_STORAGE_DELETE_ENABLED": "true"},
        healthcheck={
            "test": ["CMD", "wget", "-q", "-O", "-", "http://127.0.0.1:5000/v2/"],
            "interval": 1_000_000_000,
            "timeout": 2_000_000_000,
            "retries": 20,
        },
    )

    try:
        for _ in range(40):
            container.reload()
            if container.status == "running":
                health = container.attrs.get("State", {}).get("Health", {}).get("Status")
                if health in {None, "healthy"}:
                    break
            time.sleep(0.5)
        container.reload()
        host_port = container.attrs["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]
        base_url = f"http://127.0.0.1:{host_port}"
        yield {
            "base_url": base_url,
            "repository": runtime["repository"],
        }
    finally:
        container.remove(force=True)


def test_ensure_registry_image_uses_local_image_without_pull():
    client = Mock()
    client.images.get.return_value = object()

    _ensure_registry_image(client, "registry:2")

    client.images.get.assert_called_once_with("registry:2")
    client.images.pull.assert_not_called()


def test_ensure_registry_image_skips_when_pull_fails():
    client = Mock()
    client.images.get.side_effect = docker.errors.ImageNotFound("missing")
    client.images.pull.side_effect = docker.errors.APIError("pull failed")

    with pytest.raises(pytest.skip.Exception) as exc_info:
        _ensure_registry_image(client, "registry:2")

    assert "registry:2" in str(exc_info.value)
    assert ENV_IMAGE in str(exc_info.value)


@pytest.mark.integration
def test_real_oci_registry_artifact_round_trip(real_oci_registry_runtime):
    base_url = real_oci_registry_runtime["base_url"]
    repository = real_oci_registry_runtime["repository"]
    mirror = OciBundleMirror(f"{base_url}/{repository}")

    bundle_json = json.dumps(
        {
            "mediaType": "application/vnd.dev.sigstore.bundle.v0.3+json",
            "verificationMaterial": {"tlogEntries": [{"logIndex": 7}]},
            "content": {"messageSignature": {"messageDigest": {"algorithm": "SHA2_256", "digest": "ab" * 32}}},
        },
        sort_keys=True,
    )
    payload_b64 = "eyJ0ZXN0IjoicmVhbC1vY2ktcmVnaXN0cnkifQ=="
    payload_hash = "sha256:" + hashlib.sha256(payload_b64.encode("utf-8")).hexdigest()
    annotations = build_mirror_annotations(
        chain_id="default",
        sequence_num=2,
        event_digest="sha384:" + ("12" * 48),
        rekor_log_id="rekor-entry-123",
        payload_b64=payload_b64,
        event_id="evt-oci-real-1",
        prev_event_digest="sha384:" + ("34" * 48),
        prev_lookup_hash="sha256:" + ("56" * 32),
    )
    manifest = mirror.publish_bundle(payload_hash=payload_hash, bundle_json=bundle_json, annotations=annotations)
    resolved = mirror.resolve_bundle(payload_hash)

    assert manifest["payloadHash"] == payload_hash
    assert manifest["artifactDigest"].startswith("sha256:")
    assert resolved is not None
    assert resolved["payload_hash"] == payload_hash
    assert resolved["bundle_json"] == bundle_json
    assert resolved["artifact_digest"] == manifest["artifactDigest"]
    assert resolved["annotations"]["chain_id"] == "default"
    assert resolved["annotations"]["rekor_log_id"] == "rekor-entry-123"
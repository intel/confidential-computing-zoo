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

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

from tc_api.api.workflows import _normalize_local_oci_reference, launch_container_async
from tc_api.services import DockerService
from tc_api.verification_profiles import evaluate_profiles


class _RecordingTlog:
    def __init__(self):
        self.entries = []

    def add_entry(self, record_id, entry):
        self.entries.append(entry)


def _immutable_entry(event_id, event_type, predicate_entries):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "predicate_entries": predicate_entries,
    }


def _entry(key, value):
    return {"key": key, "value": value}


def test_launch_profile_uses_latest_launch_id_grouping():
    entries = [
        _immutable_entry(
            "evt-old-launch",
            "launch",
            [
                _entry("launch_id", "launch-old"),
                _entry("workload_id", "svc-a"),
                _entry("image_digest", "sha256:old"),
                _entry("launch_config_digest", "sha384:oldcfg"),
                _entry("privileged", True),
                _entry("network_mode", "host"),
                _entry("mounts", ["/etc/hosts:/etc/hosts"]),
                _entry("devices", []),
                _entry("capabilities", ["ALL"]),
                _entry("launch_result", "success"),
            ],
        ),
        _immutable_entry(
            "evt-old-start",
            "docker_start",
            [
                _entry("launch_id", "launch-old"),
                _entry("workload_id", "svc-a"),
                _entry("instance_id", "container-old"),
                _entry("operation_type", "start"),
                _entry("operation_result", "success"),
            ],
        ),
        _immutable_entry(
            "evt-new-launch",
            "launch",
            [
                _entry("launch_id", "launch-new"),
                _entry("workload_id", "svc-a"),
                _entry("image_digest", "sha256:new"),
                _entry("launch_config_digest", "sha384:newcfg"),
                _entry("privileged", True),
                _entry("network_mode", "host"),
                _entry("mounts", ["/etc/hosts:/etc/hosts"]),
                _entry("devices", []),
                _entry("capabilities", ["ALL"]),
                _entry("launch_result", "success"),
            ],
        ),
        _immutable_entry(
            "evt-new-start",
            "docker_start",
            [
                _entry("launch_id", "launch-new"),
                _entry("workload_id", "svc-a"),
                _entry("instance_id", "container-new"),
                _entry("operation_type", "start"),
                _entry("operation_result", "success"),
            ],
        ),
    ]

    profiles = evaluate_profiles(entries)

    assert profiles["launch"]["target_launch_id"] == "launch-new"
    assert profiles["launch"]["matched_event_ids"] == ["evt-new-launch", "evt-new-start"]


def test_launch_profile_does_not_require_instance_id_before_create():
    entries = [
        _immutable_entry(
            "evt-launch",
            "launch",
            [
                _entry("launch_id", "launch-failed"),
                _entry("workload_id", "svc-a"),
                _entry("image_digest", "sha256:new"),
                _entry("launch_config_digest", "sha384:newcfg"),
                _entry("privileged", True),
                _entry("network_mode", "host"),
                _entry("mounts", ["/etc/hosts:/etc/hosts"]),
                _entry("devices", []),
                _entry("capabilities", ["ALL"]),
                _entry("launch_result", "failed"),
            ],
        )
    ]

    profiles = evaluate_profiles(entries)

    assert profiles["launch"]["target_launch_id"] == "launch-failed"
    assert not any("instance_id" in error for error in profiles["launch"]["errors"])


def test_runtime_profile_verifies_docker_baseline_with_runtime_engine():
    entries = [
        _immutable_entry(
            "evt-runtime",
            "docker_start",
            [
                _entry("runtime_engine", "docker"),
                _entry("operation_type", "start"),
                _entry("operation_result", "success"),
                _entry("workload_id", "svc-a"),
                _entry("instance_id", "container-1"),
            ],
        )
    ]

    profiles = evaluate_profiles(entries)

    assert profiles["docktap-runtime"]["status"] == "verified"


def test_runtime_profile_missing_runtime_engine_fails():
    entries = [
        _immutable_entry(
            "evt-runtime-missing-engine",
            "docker_start",
            [
                _entry("operation_type", "start"),
                _entry("operation_result", "success"),
                _entry("workload_id", "svc-a"),
                _entry("instance_id", "container-1"),
            ],
        )
    ]

    profiles = evaluate_profiles(entries)

    assert profiles["docktap-runtime"]["status"] == "failed"
    assert any("runtime_engine" in error for error in profiles["docktap-runtime"]["errors"])


def test_runtime_profile_unknown_runtime_engine_is_incomplete():
    entries = [
        _immutable_entry(
            "evt-runtime-unknown-engine",
            "rocket_start",
            [
                _entry("runtime_engine", "rocket"),
                _entry("operation_type", "start"),
                _entry("operation_result", "success"),
                _entry("workload_id", "svc-a"),
                _entry("instance_id", "container-1"),
            ],
        )
    ]

    profiles = evaluate_profiles(entries)

    assert profiles["docktap-runtime"]["status"] == "incomplete"
    assert profiles["docktap-runtime"]["details"]["unsupported_runtime_engines"] == ["rocket"]
    assert any("Unsupported runtime_engine" in warning for warning in profiles["docktap-runtime"]["warnings"])


def test_build_image_emits_profile_fields(tmp_path):
    tlog = _RecordingTlog()
    service = DockerService()

    with patch("tc_api.services.build.BUILD_DIR", str(tmp_path)), patch("tc_api.services.build.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="built", stderr="")
        with patch.object(service, "_resolve_image_digest", side_effect=lambda image_ref: f"sha384:{image_ref}"):
            assert service.build_image("FROM python:3.11\nRUN echo hi\n", "bld-123", "alice", tlog, "rec-1") is True

    keys = [entry.key for entry in tlog.entries]
    assert "dockerfile_digest" in keys
    assert "build_context_digest" in keys
    assert "base_image_digests" in keys
    assert "build_status" in keys
    assert "output_image_digest" in keys


def test_push_image_emits_publish_profile_fields(tmp_path):
    tlog = _RecordingTlog()
    service = DockerService()

    with patch("tc_api.services.publish.subprocess.run") as mock_run:
        mock_run.return_value = SimpleNamespace(returncode=0, stdout="pushed", stderr="")
        with patch.object(service, "_resolve_image_digest", return_value="sha256:pushed"):
            assert service.push_image("oci:/tmp/build/image", "docker://registry/repo:tag", tlog, "rec-1") is True

    keys = [entry.key for entry in tlog.entries]
    assert "pushed_subject_digest" in keys
    assert "target_ref" in keys
    assert "publish_status" in keys


def test_launch_async_emits_launch_profile_fields(tmp_path):
    tlog = _RecordingTlog()
    request = SimpleNamespace(
        image_id="svc-image",
        user_id="alice",
        image_url="docker.io/example/svc-image:latest-encrypted",
        sbom_url=None,
        attestation_required=False,
        metadata={"workload_id": "svc-a"},
        model_dump=lambda: {
            "image_id": "svc-image",
            "user_id": "alice",
            "image_url": "docker.io/example/svc-image:latest-encrypted",
            "sbom_url": None,
            "attestation_required": False,
            "metadata": {"workload_id": "svc-a"},
        },
    )

    with patch("tc_api.api.workflows.docker_service._resolve_image_digest", return_value="sha256:launch"), \
        patch("tc_api.api.workflows.docker_service.pull_image", return_value=True), \
        patch("tc_api.api.workflows.docker_service.launch_containers", return_value=[{"container_ID": "container-1", "container_Status": "running"}]), \
        patch("tc_api.api.workflows.docker_service.commit_and_save_receipt", return_value=(True, "log-1")), \
        patch("tc_api.api.workflows.docker_service.verify_chain_state", return_value="success"), \
        patch("tc_api.api.workflows.docker_service.update_launch_status"), \
        patch("tc_api.api.workflows.docker_service.update_transparencylog_status"), \
        patch("sigstore.oidc.Issuer.production") as mock_production:
        mock_production.return_value.identity_token.return_value = "token"
        asyncio.run(
            launch_container_async(
                request,
                "launch-123",
                "svc-a",
                "workload-chain-svc-a",
                str(tmp_path),
                tlog,
                "rec-1",
            )
        )

    keys = [entry.key for entry in tlog.entries]
    assert "workload_id" in keys
    assert "image_digest" in keys
    assert "launch_config_digest" in keys
    assert "privileged" in keys
    assert "network_mode" in keys
    assert "mounts" in keys
    assert "devices" in keys
    assert "capabilities" in keys
    assert "launch_instance_ids" in keys


def test_normalize_local_oci_ref_for_sbom_verification(tmp_path):
    image_dir = tmp_path / "plain"
    image_dir.mkdir()
    assert _normalize_local_oci_reference(str(image_dir)) == f"oci:{image_dir}"
    assert _normalize_local_oci_reference(f"oci:{image_dir}") == f"oci:{image_dir}"
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

import base64
import os
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import tc_api.services.base as base_services
import tc_api.services.build as build_services
import tc_api.services.build as services
from tc_api.api.app import app
from tc_api.services import DockerService


class DummySigner:
    def __init__(self):
        self.entries = []

    def add_entry(self, entry):
        self.entries.append(entry)


class DummyTlog:
    def __init__(self):
        self.entries = []

    def add_entry(self, record_id, entry):
        self.entries.append((record_id, entry))


@pytest.fixture
def docker_service(tmp_path, monkeypatch):
    monkeypatch.setattr(build_services, "BUILD_DIR", str(tmp_path / "builds"))
    return DockerService()


def test_build_image_success_path(docker_service):
    tlog = DummyTlog()
    result = SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("tc_api.services.build.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1234", "alice", tlog, "rec-1")

    assert success is True
    assert docker_service.builds["bld-1234"].status == "building"


def test_build_image_uses_build_id_based_local_tag_for_email_identity(docker_service):
    tlog = DummyTlog()
    result = SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("tc_api.services.build.subprocess.run", return_value=result) as run_mock:
        success = docker_service.build_image("FROM python:3.11-slim", "bld-d95f73b", "qingchengx.zeng@intel.com", tlog, "rec-1")

    assert success is True
    build_cmd = run_mock.call_args_list[0].args[0]
    assert build_cmd[0:5] == [services.DOCKER_CMD, "build", "--no-cache", "--force-rm", "-t"]
    assert build_cmd[5] == "tc-api-build-bld-d95f73b:latest"


def test_build_image_nonzero_exit(docker_service):
    tlog = DummyTlog()
    result = SimpleNamespace(returncode=1, stdout="", stderr="docker build failed")

    with patch("tc_api.services.build.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1235", "alice", tlog, "rec-1")

    assert success is False
    assert docker_service.builds["bld-1235"].status == "building"


def test_build_image_missing_docker_binary(docker_service):
    tlog = DummyTlog()

    with patch("tc_api.services.build.subprocess.run", side_effect=FileNotFoundError):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1236", "alice", tlog, "rec-1")

    assert success is False


def test_build_image_timeout(docker_service):
    tlog = DummyTlog()

    with patch(
        "tc_api.services.build.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="docker build", timeout=600),
    ):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1237", "alice", tlog, "rec-1")

    assert success is False


def test_generate_sbom_missing_syft(docker_service):
    tlog = DummyTlog()

    with patch("tc_api.services.build.subprocess.run", side_effect=FileNotFoundError):
        sbom_path = docker_service.generate_sbom("alice-bld-1238:latest", "bld-1238", tlog, "rec-1")

    assert sbom_path is None


def test_generate_sbom_timeout(docker_service):
    tlog = DummyTlog()

    with patch(
        "tc_api.services.build.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="syft", timeout=300),
    ):
        sbom_path = docker_service.generate_sbom("alice-bld-1239:latest", "bld-1239", tlog, "rec-1")

    assert sbom_path is None


def test_create_luks_block_prepares_file_before_allocating_loop(tmp_path):
    tlog = DummyTlog()
    service = DockerService()
    vfs_path = str(tmp_path / "vfs" / "disk.img")
    calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=600, check=False):
        calls.append(cmd)
        if cmd[:2] == ["truncate", "-s"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["losetup", "--find", "--show"]:
            return SimpleNamespace(returncode=0, stdout="/dev/loop7\n", stderr="")
        if cmd[:2] == ["curl", "-fsSL"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if str(cmd[0]).endswith("create_encrypted_vfs.sh"):
            return SimpleNamespace(returncode=0, stdout="created", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("tc_api.services.luks.os.path.exists", return_value=True), patch(
        "tc_api.services.luks.subprocess.run", side_effect=fake_run
    ):
        mapper_dir, loop_device = service.create_luks_block("alice", tlog, "rec-1", "pw", "8M", vfs_path)

    assert calls[0] == ["truncate", "-s", "8M", vfs_path]
    assert calls[1] == ["losetup", "--find", "--show", vfs_path]
    assert calls[2][:2] == ["curl", "-fsSL"]
    assert str(calls[3][0]).endswith("create_encrypted_vfs.sh")
    assert len(mapper_dir) == 32
    assert loop_device == "/dev/loop7"


def test_create_luks_block_raises_script_error_and_detaches_loop(tmp_path):
    tlog = DummyTlog()
    service = DockerService()
    vfs_path = str(tmp_path / "vfs" / "disk.img")
    detach_calls = []

    def fake_run(cmd, capture_output=True, text=True, timeout=600, check=False):
        if cmd[:2] == ["truncate", "-s"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if cmd[:3] == ["losetup", "--find", "--show"]:
            return SimpleNamespace(returncode=0, stdout="/dev/loop7\n", stderr="")
        if cmd[:2] == ["curl", "-fsSL"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if str(cmd[0]).endswith("create_encrypted_vfs.sh"):
            return SimpleNamespace(returncode=1, stdout="Create 8M block file", stderr="losetup: /dev/loop7: failed to set up loop device")
        if cmd[:2] == ["losetup", "-d"]:
            detach_calls.append(cmd)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("tc_api.services.luks.os.path.exists", return_value=True), patch(
        "tc_api.services.luks.subprocess.run", side_effect=fake_run
    ):
        with pytest.raises(RuntimeError, match="failed to set up loop device"):
            service.create_luks_block("alice", tlog, "rec-1", "pw", "8M", vfs_path)

    assert detach_calls == [["losetup", "-d", "/dev/loop7"]]


def test_build_result_shows_failed_when_build_step_fails():
    payload = {
        "dockerfile": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test binary").decode(),
        "encrypt": False,
        "user_id": "unit-user",
        "sign_key": "dummy-sign-key",
        "cert": "dummy-cert",
        "identity_token": "token-123",
    }

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "unit-user",
            "subject": "unit-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "unit-user",
        },
    ):
        with TestClient(app) as client:
            with patch("tc_api.api.workflows.docker_service.build_image", return_value=False):
                submit_response = client.post("/api/build-package", json=payload)
                assert submit_response.status_code == 200
                submit_payload = submit_response.json()
                assert submit_payload["status"] == "failed"
                assert submit_payload["build_id"]
                build_id = submit_payload["build_id"]

            result_response = client.get(
                f"/api/build-result/{build_id}",
                headers={"Authorization": "Bearer token-123"},
            )
            assert result_response.status_code == 200
            result_payload = result_response.json()
            assert result_payload["status"] == "failed"
            assert result_payload["current_step"] == "Container build failed"


        def test_get_build_status_recovers_from_build_directory(docker_service, tmp_path):
            build_id = "bld-legacy1"
            build_path = tmp_path / "builds" / build_id
            artifact_path = build_path / "tc-api-build-bld-legacy1"
            artifact_path.mkdir(parents=True)
            (artifact_path / "index.json").write_text("{}", encoding="utf-8")
            (artifact_path / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}', encoding="utf-8")
            (build_path / f"{build_id}-sbom.json").write_text('{"spdxVersion":"SPDX-2.3"}', encoding="utf-8")
            (build_path / "build-commit-receipt.json").write_text(
                '{"record_id":"rec-123","event_id":"evt-123","queue_status":"pending"}',
                encoding="utf-8",
            )

            recovered = docker_service.get_build_status(build_id)

            assert recovered is not None
            assert recovered.build_id == build_id
            assert recovered.status == "success"
            assert recovered.image_id == f"oci:{artifact_path}"
            assert recovered.sbom_url == str(build_path / f"{build_id}-sbom.json")
            assert recovered.log_id == "rec-123"


def test_verify_sbom_accepts_local_oci_layout(docker_service, tmp_path):
    tlog = DummyTlog()
    image_dir = tmp_path / "plain"
    image_dir.mkdir()
    (image_dir / "index.json").write_text("{}", encoding="utf-8")
    (image_dir / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}', encoding="utf-8")
    sbom_path = tmp_path / "sbom.json"
    sbom_path.write_text('{"spdxVersion":"SPDX-2.3"}', encoding="utf-8")

    verified = docker_service.verify_sbom(f"oci:{image_dir}", str(sbom_path), tlog, "rec-1")

    assert verified is True


def test_verify_sbom_logs_cosign_failure_reason(docker_service, caplog):
    tlog = DummyTlog()
    failure = SimpleNamespace(returncode=1, stdout="", stderr="signature mismatch")

    with patch("tc_api.services.publish.subprocess.run", return_value=failure):
        with caplog.at_level("WARNING"):
            verified = docker_service.verify_sbom(
                "docker.io/trustedzoo/plain:latest-encrypted",
                "unused-sbom.json",
                tlog,
                "rec-1",
                "/home/tc_api/cosign.pub",
            )

    assert verified is False
    assert "Cosign verify failed for trustedzoo/plain:latest-encrypted: signature mismatch" in caplog.text


def test_encrypt_image_prefers_docker_daemon_transport(docker_service, tmp_path):
    tlog = DummyTlog()
    public_key = tmp_path / "enc.pub"
    public_key.write_text("pub", encoding="utf-8")
    results = [
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=0, stdout="ok", stderr=""),
    ]

    with patch.dict(os.environ, {"DOCKER_API_VERSION": "1.24"}, clear=False):
        with patch("tc_api.services.build.subprocess.run", side_effect=results) as run_mock:
            encrypted = docker_service.encrypt_image("tc-api-build-bld-1:latest", "bld-1", str(public_key), tlog, "rec-1")

    assert encrypted == f"oci:{tmp_path / 'builds' / 'bld-1' / 'tc-api-build-bld-1'}"
    validate_cmd = run_mock.call_args_list[0].args[0]
    first_cmd = run_mock.call_args_list[1].args[0]
    assert validate_cmd == ["openssl", "pkey", "-pubin", "-in", str(public_key), "-noout"]
    assert first_cmd[0:3] == [services.SKOPEO_CMD, "copy", "--encryption-key"]
    assert first_cmd[3] == f"jwe:{public_key}"
    assert first_cmd[4] == "docker-daemon:tc-api-build-bld-1:latest"
    assert first_cmd[5] == f"oci:{tmp_path / 'builds' / 'bld-1' / 'tc-api-build-bld-1'}:latest-encrypted"
    assert len(run_mock.call_args_list) == 2


def test_encrypt_image_falls_back_to_docker_archive_on_transport_error(docker_service, tmp_path):
    tlog = DummyTlog()
    public_key = tmp_path / "enc.pub"
    public_key.write_text("pub", encoding="utf-8")
    results = [
        SimpleNamespace(returncode=0, stdout="", stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="Error response from daemon: client version 1.24 is too old"),
        SimpleNamespace(returncode=0, stdout="saved", stderr=""),
        SimpleNamespace(returncode=0, stdout="encrypted", stderr=""),
    ]

    with patch.dict(os.environ, {"DOCKER_API_VERSION": "1.24"}, clear=False):
        with patch("tc_api.services.build.subprocess.run", side_effect=results) as run_mock:
            encrypted = docker_service.encrypt_image("tc-api-build-bld-2:latest", "bld-2", str(public_key), tlog, "rec-2")

    assert encrypted == f"oci:{tmp_path / 'builds' / 'bld-2' / 'tc-api-build-bld-2'}"
    validate_cmd = run_mock.call_args_list[0].args[0]
    daemon_cmd = run_mock.call_args_list[1].args[0]
    save_cmd = run_mock.call_args_list[2].args[0]
    archive_cmd = run_mock.call_args_list[3].args[0]
    archive_path = tmp_path / 'builds' / 'bld-2' / 'bld-2-image.tar'
    assert validate_cmd == ["openssl", "pkey", "-pubin", "-in", str(public_key), "-noout"]
    assert daemon_cmd[4] == "docker-daemon:tc-api-build-bld-2:latest"
    assert save_cmd == [services.DOCKER_CMD, "save", "-o", str(archive_path), "tc-api-build-bld-2:latest"]
    assert archive_cmd[4] == f"docker-archive:{archive_path}"
    assert archive_cmd[5] == f"oci:{tmp_path / 'builds' / 'bld-2' / 'tc-api-build-bld-2'}:latest-encrypted"


def test_encrypt_image_logs_invalid_public_key_before_skopeo(docker_service, tmp_path, caplog):
    tlog = DummyTlog()
    public_key = tmp_path / "enc.pub"
    public_key.write_text("not-a-public-key", encoding="utf-8")
    validation_failure = SimpleNamespace(returncode=1, stdout="", stderr="Could not read key of Public Key from file")

    with patch("tc_api.services.build.subprocess.run", return_value=validation_failure) as run_mock:
        with caplog.at_level("ERROR"):
            encrypted = docker_service.encrypt_image("alice-bld-3:latest", "bld-3", str(public_key), tlog, "rec-3")

    assert encrypted is None
    assert run_mock.call_count == 1
    assert "Encryption key validation failed for" in caplog.text


def test_download_kbs_artifact_retries_transient_connection_failures(docker_service, tmp_path, monkeypatch):
    destination = tmp_path / "openssl.pub"
    attempts = {"count": 0}

    monkeypatch.setattr(base_services, "KBS_FETCH_RETRIES", 3)
    monkeypatch.setattr(base_services, "KBS_FETCH_RETRY_DELAY_SECONDS", 0.01)

    def fake_run(cmd, capture_output=True, text=True, timeout=None, env=None):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return SimpleNamespace(returncode=7, stdout="", stderr="Failed to connect to 127.0.0.1 port 8006: Connection refused")

        destination.write_text("PUBLIC", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("tc_api.services.base.subprocess.run", side_effect=fake_run) as run_mock:
        with patch("tc_api.services.base.time.sleep") as sleep_mock:
            ok, detail = docker_service._download_kbs_artifact("http://127.0.0.1:8006/openssl.pub", str(destination))

    assert ok is True
    assert "after 2 attempts" in detail
    assert run_mock.call_count == 2
    sleep_mock.assert_called_once_with(0.01)


def test_get_pubkey_from_kbs_derives_public_key_from_key_pem(docker_service, tmp_path):
    tlog = DummyTlog()

    def fake_run(cmd, capture_output=True, text=True, timeout=None, env=None):
        if cmd[0] == "curl":
            url = cmd[2]
            destination = cmd[4]
            if url.endswith("openssl.key"):
                return SimpleNamespace(returncode=22, stdout="", stderr="404")
            if url.endswith("key.pem"):
                with open(destination, "w", encoding="utf-8") as handle:
                    handle.write("PRIVATE")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if url.endswith("cosign.key"):
                with open(destination, "w", encoding="utf-8") as handle:
                    handle.write("COSIGN-PRIVATE")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if url.endswith("cosign.pub"):
                with open(destination, "w", encoding="utf-8") as handle:
                    handle.write("COSIGN-PUBLIC")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if url.endswith("openssl.pub") or url.endswith("pub.pem"):
                return SimpleNamespace(returncode=22, stdout="", stderr="404")
            raise AssertionError(f"Unexpected curl URL: {url}")

        if cmd[:4] == ["openssl", "pkey", "-in", cmd[3]]:
            output_path = cmd[6]
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write("-----BEGIN PUBLIC KEY-----\nFAKE\n-----END PUBLIC KEY-----\n")
            return SimpleNamespace(returncode=0, stdout="derived", stderr="")

        if cmd[:4] == ["openssl", "pkey", "-pubin", "-in"]:
            return SimpleNamespace(returncode=0, stdout="public key validated", stderr="")

        raise AssertionError(f"Unexpected command: {cmd}")

    with patch("tc_api.services.base.subprocess.run", side_effect=fake_run):
        attestation_result, key_dict = docker_service.get_pubKey_from_KBS(tlog, "rec-kbs")

    assert attestation_result == "trusted"
    assert key_dict["opensslKey"].endswith("_kbs_keys/rec-kbs/openssl.key")
    assert key_dict["opensslPub"].endswith("_kbs_keys/rec-kbs/openssl.pub")
    assert key_dict["cosignKey"].endswith("_kbs_keys/rec-kbs/cosign.key")
    assert os.path.exists(key_dict["opensslPub"])


@pytest.mark.asyncio
async def test_launch_containers_normalizes_local_oci_image_id(docker_service, tmp_path):
    tlog = DummyTlog()
    results = [
        SimpleNamespace(returncode=0, stdout="copied", stderr=""),
        SimpleNamespace(returncode=0, stdout="loaded", stderr=""),
        SimpleNamespace(returncode=0, stdout="started", stderr=""),
        SimpleNamespace(returncode=0, stdout="container-1\n", stderr=""),
        SimpleNamespace(returncode=0, stdout="running\n", stderr=""),
    ]

    with patch("tc_api.services.launch.subprocess.run", side_effect=results) as run_mock:
        launched = await docker_service.launch_containers(
            tlog,
            "rec-1",
            image_url="./builds/bld-1/plain",
            image_id="oci:./builds/bld-1/plain",
            launch_pth=str(tmp_path),
            workload_id="svc-a",
            launch_id="launch-123",
        )

    assert launched == [{"container_ID": "container-1", "container_Status": "running"}]
    first_cmd = run_mock.call_args_list[0].args[0]
    third_cmd = run_mock.call_args_list[2].args[0]
    assert first_cmd[-1].endswith(":tc-api-launch-123:latest")
    assert third_cmd[-1] == "tc-api-launch-123:latest"

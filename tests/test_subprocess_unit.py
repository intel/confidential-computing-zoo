import base64
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import tc_api.services as services
from tc_api.main import app
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
    monkeypatch.setattr(services, "BUILD_DIR", str(tmp_path / "builds"))
    return DockerService()


def test_build_image_success_path(docker_service):
    signer = DummySigner()
    result = SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("tc_api.services.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1234", "alice", signer)

    assert success is True
    assert docker_service.builds["bld-1234"].status == "building"


def test_build_image_nonzero_exit(docker_service):
    signer = DummySigner()
    result = SimpleNamespace(returncode=1, stdout="", stderr="docker build failed")

    with patch("tc_api.services.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1235", "alice", signer)

    assert success is False
    assert docker_service.builds["bld-1235"].status == "building"


def test_build_image_missing_docker_binary(docker_service):
    signer = DummySigner()

    with patch("tc_api.services.subprocess.run", side_effect=FileNotFoundError):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1236", "alice", signer)

    assert success is False


def test_build_image_timeout(docker_service):
    signer = DummySigner()

    with patch(
        "tc_api.services.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="docker build", timeout=600),
    ):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1237", "alice", signer)

    assert success is False


def test_generate_sbom_missing_syft(docker_service):
    signer = DummySigner()

    with patch("tc_api.services.subprocess.run", side_effect=FileNotFoundError):
        sbom_path = docker_service.generate_sbom("alice-bld-1238:latest", "bld-1238", signer)

    assert sbom_path is None


def test_generate_sbom_timeout(docker_service):
    signer = DummySigner()

    with patch(
        "tc_api.services.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="syft", timeout=300),
    ):
        sbom_path = docker_service.generate_sbom("alice-bld-1239:latest", "bld-1239", signer)

    assert sbom_path is None


def test_build_result_shows_failed_when_build_step_fails():
    client = TestClient(app)
    payload = {
        "dockerfile": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test binary").decode(),
        "encrypt": False,
        "user_id": "unit-user",
        "sign_key": "dummy-sign-key",
        "cert": "dummy-cert",
    }

    with patch("tc_api.main.docker_service.build_image", return_value=False):
        submit_response = client.post("/api/build-package", json=payload)
        assert submit_response.status_code == 200
        build_id = submit_response.json()["build_id"]

    result_response = client.get(f"/api/build-result/{build_id}")
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["status"] == "failed"
    assert result_payload["current_step"] == "Container build failed"


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

    with patch("tc_api.services.subprocess.run", side_effect=results) as run_mock:
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

import base64
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import services
from main import app
from services import DockerService


class DummySigner:
    def __init__(self):
        self.entries = []

    def add_entry(self, entry):
        self.entries.append(entry)


@pytest.fixture
def docker_service(tmp_path, monkeypatch):
    monkeypatch.setattr(services, "BUILD_DIR", str(tmp_path / "builds"))
    return DockerService()


def test_build_image_success_path(docker_service):
    signer = DummySigner()
    result = SimpleNamespace(returncode=0, stdout="ok", stderr="")

    with patch("services.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1234", "alice", signer)

    assert success is True
    assert docker_service.builds["bld-1234"].status == "building"


def test_build_image_nonzero_exit(docker_service):
    signer = DummySigner()
    result = SimpleNamespace(returncode=1, stdout="", stderr="docker build failed")

    with patch("services.subprocess.run", return_value=result):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1235", "alice", signer)

    assert success is False
    assert docker_service.builds["bld-1235"].status == "building"


def test_build_image_missing_docker_binary(docker_service):
    signer = DummySigner()

    with patch("services.subprocess.run", side_effect=FileNotFoundError):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1236", "alice", signer)

    assert success is False


def test_build_image_timeout(docker_service):
    signer = DummySigner()

    with patch(
        "services.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="docker build", timeout=600),
    ):
        success = docker_service.build_image("FROM python:3.11-slim", "bld-1237", "alice", signer)

    assert success is False


def test_generate_sbom_missing_syft(docker_service):
    signer = DummySigner()

    with patch("services.subprocess.run", side_effect=FileNotFoundError):
        sbom_path = docker_service.generate_sbom("alice-bld-1238:latest", "bld-1238", signer)

    assert sbom_path is None


def test_generate_sbom_timeout(docker_service):
    signer = DummySigner()

    with patch(
        "services.subprocess.run",
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

    with patch("main.docker_service.build_image", return_value=False):
        submit_response = client.post("/api/build-package", json=payload)
        assert submit_response.status_code == 200
        build_id = submit_response.json()["build_id"]

    result_response = client.get(f"/api/build-result/{build_id}")
    assert result_response.status_code == 200
    result_payload = result_response.json()
    assert result_payload["status"] == "failed"
    assert result_payload["current_step"] == "Container build failed"

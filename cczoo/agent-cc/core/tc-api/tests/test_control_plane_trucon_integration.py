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
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import tc_api.api.runtime as runtime_mod
import tc_api.api.request_auth as request_auth_mod
import tc_api.api.workflows as workflow_mod
import tc_api.services.build as services_mod
from tc_api.api.app import app


def _jwt(subject: str) -> str:
    header = {"alg": "none", "typ": "JWT"}
    payload = {
        "iss": "https://oauth2.sigstore.dev/auth",
        "sub": subject,
        "aud": "sigstore",
        "iat": 2_000_000_000,
        "exp": 2_000_000_300,
    }

    def enc(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


class ControlPlaneHarness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._monkeypatch = monkeypatch
        self._build_dir = tmp_path / "builds"
        self._upload_dir = tmp_path / "uploads"
        self._logs_dir = tmp_path / "logs"

        self._build_dir.mkdir(parents=True, exist_ok=True)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

        self._monkeypatch.setattr(runtime_mod, "BUILD_DIR", str(self._build_dir))
        self._monkeypatch.setattr(runtime_mod, "UPLOAD_DIR", str(self._upload_dir))
        self._monkeypatch.setattr(runtime_mod, "LOGS_DIR", str(self._logs_dir))
        self._monkeypatch.setattr(workflow_mod, "BUILD_DIR", str(self._build_dir))
        self._monkeypatch.setattr(services_mod, "BUILD_DIR", str(self._build_dir))

        workflow_mod.docker_service.builds.clear()
        workflow_mod.docker_service.publish_results.clear()
        workflow_mod.docker_service.launches.clear()
        workflow_mod.docker_service.transparency_logs.clear()

        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "generate_uuid",
            lambda prefix="bld": f"{prefix}-test123",
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "cleanup_build_artifacts",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "update_transparencylog_status",
            lambda *args, **kwargs: None,
        )
        self._monkeypatch.setattr(
            request_auth_mod,
            "inspect_identity_token",
            lambda _token, expected_identity=None: {
                "valid_for_sigstore": True,
                "errors": [],
                "derived_identity": expected_identity,
                "subject": expected_identity,
                "issuer": "https://oauth2.sigstore.dev/auth",
                "email": expected_identity,
            },
        )

    def seed_build_result(self, *, user_id: str, build_id: str, image_id: str) -> None:
        workflow_mod.docker_service.update_build_status(
            user_id,
            build_id,
            "success",
            image_id=image_id,
            image_url=image_id,
        )

    def client(self) -> TestClient:
        return TestClient(app)

    def patch_trucon(self, *, commit_success: bool, verify_status: str) -> None:
        record_id = "rec-123" if commit_success else None
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "commit_and_save_receipt",
            lambda *args, **kwargs: (commit_success, record_id),
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "verify_chain_state",
            lambda *args, **kwargs: verify_status,
        )

    def patch_build_success(self) -> None:
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "build_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "export_image_to_oci",
            lambda *args, **kwargs: "oci:/tmp/builds/bld-test123/plain",
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "generate_sbom",
            lambda *args, **kwargs: str(self._build_dir / "bld-test123" / "bld-test123-sbom.json"),
        )

    def patch_publish_success(self) -> None:
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "push_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "get_pubKey_from_KBS",
            lambda *args, **kwargs: ("trusted", {"cosignKey": "/tmp/fake-cosign.key"}),
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "sign_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "create_sbom_attestation",
            lambda *args, **kwargs: True,
        )

    def patch_launch_success(self) -> None:
        async def _launch_containers(*args, **kwargs):
            return ["container-1"]

        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "pull_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            workflow_mod.docker_service,
            "launch_containers",
            _launch_containers,
        )


@pytest.fixture
def harness(monkeypatch, tmp_path):
    return ControlPlaneHarness(monkeypatch, tmp_path)


@pytest.fixture(autouse=True)
def patched_lifespan():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production:
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        yield


def _build_payload():
    return {
        "dockerfile": "FROM python:3.11-slim\nWORKDIR /app\nCOPY . .",
        "app_binary": base64.b64encode(b"test-binary").decode(),
        "encrypt": False,
        "user_id": "build-user",
        "identity_token": "fake-identity-token",
        "sign_key": "dummy-sign-key",
        "cert": "dummy-cert",
    }


def _publish_payload():
    return {
        "build_id": "bld-test123",
        "sbom_url": "/tmp/fake-sbom.json",
        "image_id": "oci:/tmp/test-image",
        "user_id": "publish-user",
        "identity_token": "fake-identity-token",
        "log_evidence": True,
    }


def _launch_payload():
    return {
        "image_id": "img-test123",
        "user_id": "launch-user",
        "image_url": "docker.io/example/test:latest-encrypted",
        "attestation_required": False,
        "identity_token": "fake-identity-token",
    }


def _auth_headers(token: str = "fake-identity-token"):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success")],
)
def test_build_flow_preserves_result_fields(harness, commit_success, verify_status):
    harness.patch_build_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)

    with harness.client() as client:
        response = client.post("/api/build-package", json=_build_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["build_id"] == "bld-test123"
        assert data["status"] == "submitted"
        assert data["user_id"] == "build-user"

        result = client.get("/api/build-result/bld-test123", headers=_auth_headers())

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["build_id"] == "bld-test123"
    assert result_data["status"] == "success"
    assert result_data["current_step"] == "Build completed successfully"
    assert result_data["transparencyLog_verify"] == verify_status
    assert result_data["image_url"] == "oci:/tmp/builds/bld-test123/plain"


def test_build_flow_fails_when_transparency_commit_fails(harness, monkeypatch):
    harness.patch_build_success()
    harness.patch_trucon(commit_success=False, verify_status="degraded")
    monkeypatch.setattr(
        workflow_mod.docker_service,
        "verify_chain_state",
        lambda *args, **kwargs: pytest.fail("verify_chain_state should not run when build commit fails"),
    )

    with harness.client() as client:
        response = client.post("/api/build-package", json=_build_payload())

        assert response.status_code == 200
        result = client.get("/api/build-result/bld-test123", headers=_auth_headers())

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["build_id"] == "bld-test123"
    assert result_data["status"] == "failed"
    assert result_data["current_step"] == "Transparency log commit failed"
    assert result_data["transparencyLog_verify"] == "failed"
    assert result_data["image_url"] == "oci:/tmp/builds/bld-test123/plain"
    assert result_data["error_message"] == "Build transparency log commit failed"


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success"), (False, "degraded")],
)
def test_publish_flow_preserves_result_fields(harness, commit_success, verify_status):
    harness.patch_publish_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)
    image_id = f"oci:{harness._build_dir / 'bld-test123' / 'plain'}"
    harness.seed_build_result(user_id="publish-user", build_id="bld-test123", image_id=image_id)

    with harness.client() as client:
        payload = _publish_payload()
        payload["image_id"] = image_id
        response = client.post("/api/publish-package", json=payload)

        assert response.status_code == 200
        data = response.json()
        assert data["build_id"] == "bld-test123"
        assert data["status"] == "success"
        assert data["user_id"] == "publish-user"
        assert data["transparencyLog_verify"] == verify_status
        assert data["image_id"] == "plain"

        result = client.get("/api/publish-result/bld-test123", headers=_auth_headers())

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["build_id"] == "bld-test123"
    assert result_data["status"] == "success"
    assert result_data["current_step"] == "complete publish verify"
    assert result_data["transparencyLog_verify"] == verify_status


def test_publish_flow_rejects_cross_owner_access(harness):
    harness.patch_publish_success()
    harness.patch_trucon(commit_success=True, verify_status="success")
    image_id = f"oci:{harness._build_dir / 'bld-test123' / 'plain'}"
    harness.seed_build_result(user_id="alice", build_id="bld-test123", image_id=image_id)

    with harness.client() as client:
        payload = _publish_payload()
        payload["image_id"] = image_id
        response = client.post("/api/publish-package", json=payload)

    assert response.status_code == 403
    assert "does not own" in response.json()["detail"]


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success"), (False, "degraded")],
)
def test_launch_flow_preserves_result_fields(harness, commit_success, verify_status):
    harness.patch_launch_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)

    with harness.client() as client:
        response = client.post("/api/deploy-launch", json=_launch_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["launch_id"] == "launch-test123"
        assert data["status"] == "initiated"
        assert data["user_id"] == "launch-user"

        result = client.get("/api/launch-result/launch-test123", headers=_auth_headers())

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["launch_id"] == "launch-test123"
    assert result_data["status"] == "success"
    assert result_data["transparencyLog_verify"] == verify_status
    assert result_data["instance_ids"] == ["container-1"]


def test_build_result_allows_unauthenticated_reads(harness):
    harness.patch_build_success()
    harness.patch_trucon(commit_success=True, verify_status="success")

    with harness.client() as client:
        response = client.post("/api/build-package", json=_build_payload())

        assert response.status_code == 200
        result = client.get("/api/build-result/bld-test123")

    assert result.status_code == 200
    assert result.json()["build_id"] == "bld-test123"


def test_build_result_ignores_reader_identity_headers(harness, monkeypatch):
    harness.patch_build_success()
    harness.patch_trucon(commit_success=True, verify_status="success")

    with harness.client() as client:
        response = client.post("/api/build-package", json=_build_payload())

        assert response.status_code == 200

        def _inspect_identity_token(_token, expected_identity=None):
            return {
                "valid_for_sigstore": True,
                "errors": [] if expected_identity == "other-user" else ["owner mismatch"],
                "derived_identity": "other-user",
                "subject": "other-user",
                "issuer": "https://oauth2.sigstore.dev/auth",
                "email": "other-user",
            }

        monkeypatch.setattr(request_auth_mod, "inspect_identity_token", _inspect_identity_token)
        result = client.get("/api/build-result/bld-test123", headers=_auth_headers("wrong-token"))

    assert result.status_code == 200
    assert result.json()["build_id"] == "bld-test123"
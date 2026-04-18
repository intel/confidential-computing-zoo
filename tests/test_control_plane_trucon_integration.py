import base64
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import tc_api.main as main_mod
import tc_api.services as services_mod


class ControlPlaneHarness:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        self._monkeypatch = monkeypatch
        self._build_dir = tmp_path / "builds"
        self._upload_dir = tmp_path / "uploads"
        self._logs_dir = tmp_path / "logs"

        self._build_dir.mkdir(parents=True, exist_ok=True)
        self._upload_dir.mkdir(parents=True, exist_ok=True)
        self._logs_dir.mkdir(parents=True, exist_ok=True)

        self._monkeypatch.setattr(main_mod, "BUILD_DIR", str(self._build_dir))
        self._monkeypatch.setattr(main_mod, "UPLOAD_DIR", str(self._upload_dir))
        self._monkeypatch.setattr(main_mod, "LOGS_DIR", str(self._logs_dir))
        self._monkeypatch.setattr(services_mod, "BUILD_DIR", str(self._build_dir))

        main_mod.docker_service.builds.clear()
        main_mod.docker_service.publishs.clear()
        main_mod.docker_service.launchs.clear()
        main_mod.docker_service.transparencyLog.clear()

        self._monkeypatch.setattr(
            main_mod.docker_service,
            "generate_uuid",
            lambda prefix="bld": f"{prefix}-test123",
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "cleanup_build_artifacts",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "update_transparencylog_status",
            lambda *args, **kwargs: None,
        )

    def client(self) -> TestClient:
        return TestClient(main_mod.app)

    def patch_trucon(self, *, commit_success: bool, verify_status: str) -> None:
        record_id = "rec-123" if commit_success else None
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "commit_and_save_receipt",
            lambda *args, **kwargs: (commit_success, record_id),
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "verify_chain_state",
            lambda *args, **kwargs: verify_status,
        )

    def patch_build_success(self) -> None:
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "build_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "generate_sbom",
            lambda *args, **kwargs: str(self._build_dir / "bld-test123" / "bld-test123-sbom.json"),
        )

    def patch_publish_success(self) -> None:
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "push_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "get_pubKey_from_KBS",
            lambda *args, **kwargs: ("trusted", {"cosignKey": "/tmp/fake-cosign.key"}),
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "sign_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "create_sbom_attestation",
            lambda *args, **kwargs: True,
        )

    def patch_launch_success(self) -> None:
        async def _launch_containers(*args, **kwargs):
            return ["container-1"]

        self._monkeypatch.setattr(
            main_mod.docker_service,
            "pull_image",
            lambda *args, **kwargs: True,
        )
        self._monkeypatch.setattr(
            main_mod.docker_service,
            "launch_containers",
            _launch_containers,
        )


@pytest.fixture
def harness(monkeypatch, tmp_path):
    return ControlPlaneHarness(monkeypatch, tmp_path)


@pytest.fixture
def patched_lifespan():
    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
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
        "sign_key": "dummy-sign-key",
        "cert": "dummy-cert",
    }


def _publish_payload():
    return {
        "build_id": "bld-test123",
        "sbom_url": "/tmp/fake-sbom.json",
        "image_id": "oci:/tmp/test-image",
        "user_id": "publish-user",
        "log_evidence": True,
    }


def _launch_payload():
    return {
        "image_id": "img-test123",
        "user_id": "launch-user",
        "image_url": "docker.io/example/test:latest-encrypted",
        "attestation_required": False,
    }


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success"), (False, "degraded")],
)
def test_build_flow_preserves_result_fields(harness, patched_lifespan, commit_success, verify_status):
    harness.patch_build_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)

    with harness.client() as client:
        response = client.post("/api/build-package", json=_build_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["build_id"] == "bld-test123"
        assert data["status"] == "submitted"
        assert data["user_id"] == "build-user"

        result = client.get("/api/build-result/bld-test123")

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["build_id"] == "bld-test123"
    assert result_data["status"] == "success"
    assert result_data["current_step"] == "Build completed successfully"
    assert result_data["transparencyLog_verify"] == verify_status
    assert "image_url" in result_data


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success"), (False, "degraded")],
)
def test_publish_flow_preserves_result_fields(harness, patched_lifespan, commit_success, verify_status):
    harness.patch_publish_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)

    with harness.client() as client:
        response = client.post("/api/publish-package", json=_publish_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["build_id"] == "bld-test123"
        assert data["status"] == "success"
        assert data["user_id"] == "publish-user"
        assert data["transparencyLog_verify"] == verify_status
        assert data["image_id"] == "test-image"

        result = client.get("/api/publish-result/bld-test123")

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["build_id"] == "bld-test123"
    assert result_data["status"] == "success"
    assert result_data["current_step"] == "complete publish verify"
    assert result_data["transparencyLog_verify"] == verify_status


@pytest.mark.parametrize(
    ("commit_success", "verify_status"),
    [(True, "success"), (False, "degraded")],
)
def test_launch_flow_preserves_result_fields(harness, patched_lifespan, commit_success, verify_status):
    harness.patch_launch_success()
    harness.patch_trucon(commit_success=commit_success, verify_status=verify_status)

    with harness.client() as client:
        response = client.post("/api/deploy-launch", json=_launch_payload())

        assert response.status_code == 200
        data = response.json()
        assert data["launch_id"] == "launch-test123"
        assert data["status"] == "initiated"
        assert data["user_id"] == "launch-user"

        result = client.get("/api/launch-result/launch-test123")

    assert result.status_code == 200
    result_data = result.json()
    assert result_data["launch_id"] == "launch-test123"
    assert result_data["status"] == "success"
    assert result_data["transparencyLog_verify"] == verify_status
    assert result_data["instance_ids"] == ["container-1"]
import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import tc_api.api.workflows as workflow_mod
from tc_api.api.sigstore_support import _missing_sigstore_identity_detail, _resolve_required_sigstore_identity_token
from tc_api.api.app import app
from tc_api.identity.sigstore_identity import MissingSigstoreIdentityTokenError


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def test_required_sigstore_identity_uses_request_token():
    assert _resolve_required_sigstore_identity_token("build", "request-token") == "request-token"


def test_startup_fails_when_default_chain_baseline_is_required_and_init_fails():
    with patch("tc_api.api.runtime.INIT_DEFAULT_CHAIN_ON_STARTUP", True), patch(
        "tc_api.transparency.commit_client.TrustedLogAPI.init_chain",
        side_effect=RuntimeError("missing baseline token"),
    ):
        with pytest.raises(RuntimeError, match="Default-chain baseline initialization failed during startup"):
            with TestClient(app):
                pass


def test_required_sigstore_identity_returns_http_400_when_missing():
    with patch(
        "tc_api.api.sigstore_support.resolve_sigstore_identity_token",
        side_effect=MissingSigstoreIdentityTokenError("build"),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _resolve_required_sigstore_identity_token("build", None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == _missing_sigstore_identity_detail("build")


def test_missing_sigstore_identity_detail_includes_interactive_urls():
    detail = _missing_sigstore_identity_detail("publish")

    assert detail["open_in_browser_url"] is None
    assert detail["after_login_open_url"] is None
    assert detail["paste_back_url_prefix"] == "https://oauth2.sigstore.dev/auth/callback"
    assert detail["interactive_login_url"] == "/api/sigstore/interactive-login?operation=publish"
    assert detail["interactive_token_url"] == "/api/sigstore/identity-token?operation=publish&flow=copy-url"
    assert detail["interactive_callback_url"] == "/api/sigstore/callback"
    assert detail["sigstore_callback_url"] == "https://oauth2.sigstore.dev/auth/callback"


def test_sigstore_identity_token_start_endpoint_returns_auth_url():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.sigstore_support._start_sigstore_login",
        return_value={
            "operation": "build",
            "status": "browser_login_pending",
            "flow": "copy-url",
            "session_id": "sess-123",
            "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore",
            "state": "state-123",
            "redirect_uri": "https://oauth2.sigstore.dev/auth/callback",
            "expires_at": "2026-04-30T00:00:00Z",
            "message": "Open auth_url and sign in.",
            "completion_hint": "copy the final browser URL and submit it back to the server",
            "interactive_login_url": "/api/sigstore/interactive-login?operation=build",
            "callback_url": "/api/sigstore/callback",
            "sigstore_callback_url": "https://oauth2.sigstore.dev/auth/callback",
        },
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            response = client.get("/api/sigstore/identity-token?operation=build&flow=copy-url")

    assert response.status_code == 200
    data = response.json()
    assert data["operation"] == "build"
    assert data["status"] == "browser_login_pending"
    assert data["flow"] == "copy-url"
    assert data["session_id"] == "sess-123"
    assert data["auth_url"].startswith("https://oauth2.sigstore.dev/auth")
    assert data["redirect_uri"] == "https://oauth2.sigstore.dev/auth/callback"
    assert data["callback_url"] == "/api/sigstore/callback"
    assert data["sigstore_callback_url"] == "https://oauth2.sigstore.dev/auth/callback"
    assert data["interactive_login_url"] == "/api/sigstore/interactive-login?operation=build"


def test_sigstore_callback_page_returns_token_metadata():
    token = _jwt({
        "iss": "https://oauth2.sigstore.dev/auth",
        "sub": "alice@example.com",
        "aud": "sigstore",
        "iat": 1_700_000_000,
        "exp": 1_700_000_300,
    })

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.sigstore_support._get_sigstore_login_session_by_state",
        return_value={"operation": "build", "session_id": "sess-123"},
    ), patch(
        "tc_api.api.sigstore_support._exchange_sigstore_verification_code",
        return_value={
            "operation": "build",
            "status": "token_ready",
            "session_id": "sess-123",
            "identity_token": token,
            "source": "verification_code",
            "derived_identity": "alice@example.com",
            "expires_at": "2026-04-30T00:00:00Z",
            "expires_in_seconds": 300,
            "interactive_login_url": "/api/sigstore/interactive-login?operation=build",
        },
    ):
        mock_production.return_value.identity_token.return_value = token
        with TestClient(app) as client:
            response = client.get("/api/sigstore/callback?code=code-123&state=state-123")

    assert response.status_code == 200
    assert "Sigstore Login Complete" in response.text
    assert token in response.text
    assert "postMessage" in response.text


def test_sigstore_interactive_login_page_references_token_endpoint():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production:
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            response = client.get("/api/sigstore/interactive-login?operation=launch")

    assert response.status_code == 200
    assert "/api/sigstore/identity-token?operation=launch&amp;flow=copy-url" in response.text
    assert "/api/sigstore/identity-token?operation=launch&amp;flow=server-callback" in response.text
    assert "Start SSH/Remote Login" in response.text
    assert "Start Direct Callback Login" in response.text
    assert "starts with https://oauth2.sigstore.dev/auth/callback" in response.text


def test_sigstore_interactive_login_page_can_continue_existing_session():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.sigstore_support._get_sigstore_login_session",
        return_value={
            "session_id": "sess-123",
            "operation": "build",
            "flow": "copy-url",
            "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore&state=state-123",
        },
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            response = client.get("/api/sigstore/interactive-login?operation=build&session_id=sess-123")

    assert response.status_code == 200
    assert "sess-123" in response.text
    assert "https://oauth2.sigstore.dev/auth?client_id=sigstore&amp;state=state-123" in response.text


def test_sigstore_identity_token_complete_accepts_provider_callback_url():
    token = _jwt({
        "iss": "https://oauth2.sigstore.dev/auth",
        "sub": "alice@example.com",
        "aud": "sigstore",
        "iat": 1_700_000_000,
        "exp": 1_700_000_300,
    })

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.sigstore_support._complete_sigstore_login_from_redirect_url",
        return_value={
            "operation": "build",
            "status": "token_ready",
            "session_id": "sess-123",
            "identity_token": token,
            "source": "verification_code",
            "derived_identity": "alice@example.com",
            "expires_at": "2026-04-30T00:00:00Z",
            "expires_in_seconds": 300,
            "interactive_login_url": "/api/sigstore/interactive-login?operation=build",
        },
    ):
        mock_production.return_value.identity_token.return_value = token
        with TestClient(app) as client:
            response = client.post(
                "/api/sigstore/identity-token",
                json={
                    "operation": "build",
                    "session_id": "sess-123",
                    "redirect_url": "https://oauth2.sigstore.dev/auth/callback?code=code-123&state=state-123",
                },
            )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "token_ready"
    assert data["identity_token"] == token


def test_build_package_submits_when_token_missing_without_interactive_login():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.workflows.resolve_sigstore_identity_token",
        return_value=None,
    ) as resolve_token, patch(
        "tc_api.api.sigstore_support._start_sigstore_login",
    ) as start_login, patch(
        "tc_api.api.workflows.build_container_async",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["build_id"] == "bld-123"
    assert data["status"] == "submitted"
    assert resolve_token.call_args.kwargs["allow_interactive"] is False
    start_login.assert_not_called()


def test_create_luks_skips_interactive_sigstore_login_when_token_missing():
    payload = {
        "user_id": "test-user",
        "passwd": "/root/luks-key",
        "vfs_path": "/root/vfs",
        "vfs_size": "1G",
    }

    class DummyTrustedLog:
        def init_record(self):
            return SimpleNamespace(record_id="rec-123")

        def add_entry(self, *args, **kwargs):
            return None

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.luks_support.resolve_sigstore_identity_token",
        return_value=None,
    ) as resolve_token, patch(
        "tc_api.api.luks_support.docker_service.create_luks_block",
        return_value=("/dev/mapper/test-user", "/dev/loop0"),
    ), patch(
        "tc_api.api.luks_support.docker_service.commit_and_save_receipt"
    ) as commit_receipt, patch(
        "tc_api.api.luks_support.docker_service.verify_chain_state"
    ) as verify_chain_state, patch(
        "tc_api.api.luks_support.docker_service.update_luks_status"
    ) as update_luks_status:
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            client.app.state.trusted_log = DummyTrustedLog()
            response = client.post("/api/create_luks", json=payload)

    assert response.status_code == 200
    assert response.json()["mapper_dir"] == "/dev/mapper/test-user"
    assert response.json()["loop_device"] == "/dev/loop0"
    assert resolve_token.call_args.kwargs["allow_interactive"] is False
    commit_receipt.assert_not_called()
    verify_chain_state.assert_not_called()
    update_luks_status.assert_called_once_with(
        "test-user",
        "create success",
        step="create_luks completed successfully",
        log_id=None,
        transparencyLog_verify="skipped",
    )


def test_build_package_accepts_missing_app_binary():
    payload = {
        "dockerfile": "FROM busybox\nCMD [\"sh\", \"-c\", \"echo ok\"]\n",
        "encrypt": False,
        "user_id": "test-user",
        "identity_token": "token-123",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.workflows.build_container_async",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["build_id"] == "bld-123"
    assert data["status"] == "submitted"


def test_build_container_async_skips_transparency_receipt_when_token_missing():
    request = workflow_mod.BuildPackageRequest(
        dockerfile="FROM busybox\nCMD [\"sh\", \"-c\", \"echo ok\"]\n",
        encrypt=False,
        user_id="test-user",
        sign_key="dummy-sign-key",
        cert="dummy-cert",
        identity_token=None,
    )

    tlog = SimpleNamespace(add_entry=lambda *args, **kwargs: None)

    with patch("tc_api.api.workflows.docker_service.update_build_status") as update_build_status, patch(
        "tc_api.api.workflows.docker_service.build_image",
        return_value=True,
    ), patch(
        "tc_api.api.workflows.docker_service.generate_sbom",
        return_value="/tmp/bld-123/sbom.json",
    ), patch(
        "tc_api.api.workflows.docker_service.export_image_to_oci",
        return_value="oci:./builds/bld-123/test-user-bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.commit_and_save_receipt"
    ) as commit_receipt, patch(
        "tc_api.api.workflows.docker_service.verify_chain_state"
    ) as verify_chain_state:
        workflow_mod.build_container_async(request, "bld-123", tlog, "rec-123")

    commit_receipt.assert_not_called()
    verify_chain_state.assert_not_called()
    success_call = update_build_status.call_args_list[-1]
    assert success_call.args[:3] == ("test-user", "bld-123", "success")
    assert success_call.kwargs["transparencyLog_verify"] == "skipped"
    assert success_call.kwargs["log_id"] is None
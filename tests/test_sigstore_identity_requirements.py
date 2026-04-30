import base64
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import tc_api.main as main_mod
from tc_api.main import _missing_sigstore_identity_detail, _resolve_required_sigstore_identity_token
from tc_api.sigstore_identity import MissingSigstoreIdentityTokenError


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def test_required_sigstore_identity_uses_request_token():
    assert _resolve_required_sigstore_identity_token("build", "request-token") == "request-token"


def test_required_sigstore_identity_returns_http_400_when_missing():
    with patch(
        "tc_api.main.resolve_sigstore_identity_token",
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
    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main._start_sigstore_login",
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
        with TestClient(main_mod.app) as client:
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

    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main._get_sigstore_login_session_by_state",
        return_value={"operation": "build", "session_id": "sess-123"},
    ), patch(
        "tc_api.main._exchange_sigstore_verification_code",
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
        with TestClient(main_mod.app) as client:
            response = client.get("/api/sigstore/callback?code=code-123&state=state-123")

    assert response.status_code == 200
    assert "Sigstore Login Complete" in response.text
    assert token in response.text
    assert "postMessage" in response.text


def test_sigstore_interactive_login_page_references_token_endpoint():
    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production:
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(main_mod.app) as client:
            response = client.get("/api/sigstore/interactive-login?operation=launch")

    assert response.status_code == 200
    assert "/api/sigstore/identity-token?operation=launch&amp;flow=copy-url" in response.text
    assert "/api/sigstore/identity-token?operation=launch&amp;flow=server-callback" in response.text
    assert "Start SSH/Remote Login" in response.text
    assert "Start Direct Callback Login" in response.text
    assert "starts with https://oauth2.sigstore.dev/auth/callback" in response.text


def test_sigstore_interactive_login_page_can_continue_existing_session():
    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main._get_sigstore_login_session",
        return_value={
            "session_id": "sess-123",
            "operation": "build",
            "flow": "copy-url",
            "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore&state=state-123",
        },
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(main_mod.app) as client:
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

    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main._complete_sigstore_login_from_redirect_url",
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
        with TestClient(main_mod.app) as client:
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


def test_build_package_returns_interactive_guidance_when_token_missing():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
    }

    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main.resolve_sigstore_identity_token",
        side_effect=MissingSigstoreIdentityTokenError("build"),
    ), patch(
        "tc_api.main._start_sigstore_login",
        return_value={
            "operation": "build",
            "status": "browser_login_pending",
            "flow": "copy-url",
            "session_id": "sess-123",
            "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore&state=state-123",
            "state": "state-123",
            "redirect_uri": "https://oauth2.sigstore.dev/auth/callback",
            "expires_at": "2026-04-30T00:00:00Z",
            "message": "Open auth_url and sign in.",
            "interactive_login_url": "/api/sigstore/interactive-login?operation=build",
            "callback_url": "/api/sigstore/callback",
            "sigstore_callback_url": "https://oauth2.sigstore.dev/auth/callback",
        },
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(main_mod.app) as client:
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["interactive_login_url"] == "/api/sigstore/interactive-login?operation=build"
    assert detail["sigstore_callback_url"] == "https://oauth2.sigstore.dev/auth/callback"
    assert detail["open_in_browser_url"].startswith("https://oauth2.sigstore.dev/auth")
    assert detail["after_login_open_url"] == "http://testserver/api/sigstore/interactive-login?operation=build&session_id=sess-123"
    assert detail["auth_url"].startswith("https://oauth2.sigstore.dev/auth")
    assert detail["session_id"] == "sess-123"
    assert detail["redirect_uri"] == "https://oauth2.sigstore.dev/auth/callback"
    assert detail["login_status"] == "browser_login_pending"
    assert detail["flow"] == "copy-url"
    assert detail["complete_login_url"] == "/api/sigstore/identity-token"
    assert detail["interactive_continue_url"] == "/api/sigstore/interactive-login?operation=build&session_id=sess-123"


def test_build_package_accepts_missing_app_binary():
    payload = {
        "dockerfile": "FROM busybox\nCMD [\"sh\", \"-c\", \"echo ok\"]\n",
        "encrypt": False,
        "user_id": "test-user",
        "identity_token": "token-123",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.tlog_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.main.build_container_async",
        return_value=None,
    ), patch(
        "tc_api.main.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.main.docker_service.update_build_status",
        return_value=None,
    ):
        mock_production.return_value.identity_token.return_value = "fake-identity-token"
        with TestClient(main_mod.app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["build_id"] == "bld-123"
    assert data["status"] == "submitted"
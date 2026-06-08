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
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

import tc_api.api.workflows as workflow_mod
from tc_api.api.sigstore_support import _missing_sigstore_identity_detail, _resolve_required_sigstore_identity_token
from tc_api.api.app import app
from tc_api.config import BUILD_PACKAGE_MAX_REQUEST_BYTES, LUKS_VFS_BASE_DIR
from tc_api.identity.sigstore_identity import MissingSigstoreIdentityTokenError
from tc_api.models import GetTransparencyRequest, LaunchRequest, PublishPackageRequest
from tc_api.services.base import BaseDockerService


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
    with pytest.raises(HTTPException) as exc_info:
        _resolve_required_sigstore_identity_token("build", None)

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == _missing_sigstore_identity_detail("build")


def test_commit_identity_token_resolution_rejects_missing_token_before_sigstore():
    service = BaseDockerService()

    with patch("tc_api.services.base.resolve_sigstore_identity_token", return_value=None) as resolve_token:
        with pytest.raises(MissingSigstoreIdentityTokenError, match="Sigstore identity token is required for build"):
            service._resolve_commit_identity_token("build", None)

    resolve_token.assert_called_once_with("build", allow_interactive=True, require_token=True)


def test_commit_identity_token_resolution_refreshes_token_by_default():
    service = BaseDockerService()

    with patch("tc_api.services.base.resolve_sigstore_identity_token", return_value="fresh-token") as resolve_token, patch(
        "tc_api.services.base.inspect_identity_token",
        return_value={"valid_for_sigstore": True, "errors": []},
    ):
        token = service._resolve_commit_identity_token("build", None)

    assert token == "fresh-token"
    resolve_token.assert_called_once_with("build", allow_interactive=True, require_token=True)


def test_commit_identity_token_resolution_rejects_malformed_request_token_before_sigstore():
    service = BaseDockerService()

    with patch("tc_api.services.base.resolve_sigstore_identity_token", return_value=None):
        with pytest.raises(ValueError, match="malformed or missing claims"):
            service._resolve_commit_identity_token("build", "not-a-jwt")


def test_commit_identity_token_resolution_requires_refresh_for_expired_request_token():
    service = BaseDockerService()

    with patch("tc_api.services.base.resolve_sigstore_identity_token", return_value=None), patch(
        "tc_api.services.base.inspect_identity_token",
        return_value={
            "valid_for_sigstore": False,
            "errors": ["Identity token is malformed or missing claims", "Token has already expired."],
        },
    ):
        with pytest.raises(MissingSigstoreIdentityTokenError, match="client-side challenge"):
            service._resolve_commit_identity_token("build", "expired-token")


def test_commit_and_save_receipt_stores_specific_commit_error():
    service = BaseDockerService()

    with patch("tc_api.services.base.resolve_sigstore_identity_token", return_value=None):
        ok, record_id = service.commit_and_save_receipt(
            "build",
            "bld-123",
            tlog=SimpleNamespace(),
            record_id="rec-123",
            identity_token_str="not-a-jwt",
        )

    assert ok is False
    assert record_id is None
    assert "malformed or missing claims" in service.get_commit_error("build", "bld-123")


def test_commit_and_save_receipt_reclassifies_blank_signing_failure_as_sigstore_challenge():
    service = BaseDockerService()
    tlog = SimpleNamespace(commit_record=lambda **kwargs: (_ for _ in ()).throw(AssertionError()))

    with patch.object(service, "_resolve_commit_identity_token", return_value="expired-token"), patch(
        "tc_api.services.base.inspect_identity_token",
        return_value={
            "valid_for_sigstore": False,
            "errors": ["Token has already expired.", "Identity token is not within its validity period"],
        },
    ):
        ok, record_id = service.commit_and_save_receipt(
            "publish",
            "bld-123",
            tlog=tlog,
            record_id="rec-123",
            identity_token_str="expired-token",
            expected_identity="alice",
        )

    assert ok is False
    assert record_id is None
    assert "client-side challenge flow" in service.get_commit_error("publish", "bld-123")


def test_commit_and_save_receipt_preserves_exception_type_when_message_is_blank():
    service = BaseDockerService()
    tlog = SimpleNamespace(commit_record=lambda **kwargs: (_ for _ in ()).throw(AssertionError()))

    with patch.object(service, "_resolve_commit_identity_token", return_value="still-valid-token"), patch(
        "tc_api.services.base.inspect_identity_token",
        return_value={"valid_for_sigstore": True, "errors": []},
    ):
        ok, record_id = service.commit_and_save_receipt(
            "publish",
            "bld-123",
            tlog=tlog,
            record_id="rec-123",
            identity_token_str="still-valid-token",
            expected_identity="alice",
        )

    assert ok is False
    assert record_id is None
    assert service.get_commit_error("publish", "bld-123") == "AssertionError"


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


def test_build_package_accepts_cached_identity_token_without_request_token():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.resolve_sigstore_identity_token",
        return_value="cached-identity-token",
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "alice@example.com",
            "subject": "alice@example.com",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "alice@example.com",
        },
    ), patch(
        "tc_api.api.workflows.build_container_sync",
        return_value={"success": True, "transparencyLog_verify": "success"},
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["build_id"] == "bld-123"
    assert data["status"] == "success"
    assert data["user_id"] == "alice@example.com"


def test_build_package_accepts_missing_user_id_when_cached_identity_exists():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.resolve_sigstore_identity_token",
        return_value="cached-identity-token",
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "alice@example.com",
            "subject": "alice@example.com",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "alice@example.com",
        },
    ), patch(
        "tc_api.api.workflows.build_container_sync",
        return_value={"success": True, "transparencyLog_verify": "success"},
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == "alice@example.com"


def test_build_package_warns_when_user_id_differs_from_cached_identity(caplog):
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with caplog.at_level("WARNING"):
        with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
            "tc_api.api.request_auth.resolve_sigstore_identity_token",
            return_value="cached-identity-token",
        ), patch(
            "tc_api.api.request_auth.inspect_identity_token",
            return_value={
                "valid_for_sigstore": True,
                "errors": [],
                "derived_identity": "alice@example.com",
                "subject": "alice@example.com",
                "issuer": "https://oauth2.sigstore.dev/auth",
                "email": "alice@example.com",
            },
        ), patch(
            "tc_api.api.workflows.build_container_sync",
            return_value={"success": True, "transparencyLog_verify": "success"},
        ), patch(
            "tc_api.api.workflows.docker_service.generate_uuid",
            return_value="bld-123",
        ), patch(
            "tc_api.api.workflows.docker_service.update_build_status",
            return_value=None,
        ):
            with TestClient(app) as client:
                client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
                client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
                response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    assert response.json()["user_id"] == "alice@example.com"
    assert "Ignoring caller-supplied user_id 'test-user' for build; using authenticated identity 'alice@example.com'" in caplog.text


def test_build_package_rejects_missing_identity_token_when_no_cached_fallback_exists():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.resolve_sigstore_identity_token",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["operation"] == "build"
    assert "identity token is required" in detail["error"].lower()


def test_build_package_returns_sigstore_commit_challenge_for_client_side_retry():
    payload = {
        "dockerfile": "FROM python:3.11-slim",
        "app_binary": "dGVzdA==",
        "encrypt": False,
        "user_id": "test-user",
        "identity_token": "header.payload.signature",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "test-user",
            "subject": "test-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "test-user",
        },
    ), patch(
        "tc_api.api.workflows.build_container_sync",
        return_value={"success": False, "sigstore_login_required": True, "build_id": "bld-123"},
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ):
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 428
    detail = response.json()["detail"]
    assert detail["build_id"] == "bld-123"
    assert detail["retry_method"] == "POST"
    assert detail["retry_path"] == "/api/build-package/commit/bld-123"


def test_launch_result_returns_sigstore_commit_challenge_for_client_side_retry():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.workflows.docker_service.get_launch_status",
        return_value=SimpleNamespace(launch_id="launch-123", status="signing"),
    ), patch(
        "tc_api.api.workflows.docker_service.get_pending_launch_commit",
        return_value={"record_id": "rec-123", "user_id": "test-user", "chain_id": "default"},
    ):
        with TestClient(app) as client:
            response = client.get("/api/launch-result/launch-123")

    assert response.status_code == 428
    detail = response.json()["detail"]
    assert detail["launch_id"] == "launch-123"
    assert detail["retry_method"] == "POST"
    assert detail["retry_path"] == "/api/deploy-launch/commit/launch-123"


def test_publish_package_returns_sigstore_commit_challenge_for_client_side_retry():
    image_ref = f"oci:{workflow_mod.BUILD_DIR}/bld-123/plain"
    payload = {
        "build_id": "bld-123",
        "sbom_url": "/tmp/sbom.json",
        "image_id": image_ref,
        "user_id": "test-user",
        "identity_token": "header.payload.signature",
        "luks_path": "",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")
    fake_build = SimpleNamespace(user_id="test-user", image_id=image_ref)

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "test-user",
            "subject": "test-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "test-user",
        },
    ), patch(
        "tc_api.api.workflows.docker_service.get_build_status",
        return_value=fake_build,
    ), patch(
        "tc_api.api.workflows.Path.exists",
        return_value=True,
    ), patch(
        "tc_api.api.workflows.docker_service.update_publish_status",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.push_image",
        return_value=True,
    ), patch(
        "tc_api.api.workflows.docker_service.get_pubKey_from_KBS",
        return_value=("trusted", None),
    ), patch(
        "tc_api.api.workflows.docker_service.commit_and_save_receipt",
        return_value=(False, None),
    ), patch(
        "tc_api.api.workflows.docker_service.get_commit_error",
        return_value="Sigstore identity token is required for publish. Defer login to the client-side challenge flow and retry with a fresh identity_token.",
    ), patch(
        "tc_api.api.workflows.docker_service.register_pending_publish_commit",
        return_value=None,
    ):
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/publish-package", json=payload)

    assert response.status_code == 428
    detail = response.json()["detail"]
    assert detail["build_id"] == "bld-123"
    assert detail["retry_method"] == "POST"
    assert detail["retry_path"] == "/api/publish-package/commit/bld-123"


def test_publish_package_registers_stable_idempotency_key_for_resume():
    image_ref = f"oci:{workflow_mod.BUILD_DIR}/bld-123/plain"
    payload = {
        "build_id": "bld-123",
        "sbom_url": "/tmp/sbom.json",
        "image_id": image_ref,
        "user_id": "test-user",
        "identity_token": "header.payload.signature",
        "luks_path": "",
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")
    fake_build = SimpleNamespace(user_id="test-user", image_id=image_ref)

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "test-user",
            "subject": "test-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "test-user",
        },
    ), patch(
        "tc_api.api.workflows.docker_service.get_build_status",
        return_value=fake_build,
    ), patch(
        "tc_api.api.workflows.Path.exists",
        return_value=True,
    ), patch(
        "tc_api.api.workflows.docker_service.update_publish_status",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.push_image",
        return_value=True,
    ), patch(
        "tc_api.api.workflows.docker_service.get_pubKey_from_KBS",
        return_value=("trusted", None),
    ), patch(
        "tc_api.api.workflows.docker_service.commit_and_save_receipt",
        return_value=(False, None),
    ) as commit_receipt, patch(
        "tc_api.api.workflows.docker_service.get_commit_error",
        return_value="Sigstore identity token is required for publish. Defer login to the client-side challenge flow and retry with a fresh identity_token.",
    ), patch(
        "tc_api.api.workflows.docker_service.register_pending_publish_commit",
        return_value=None,
    ) as register_pending:
        with TestClient(app) as client:
            client.app.state.trusted_log.init_record = lambda context=None: fake_ctx
            client.app.state.trusted_log.add_entry = lambda *args, **kwargs: None
            response = client.post("/api/publish-package", json=payload)

    assert response.status_code == 428
    commit_receipt.assert_called_once()
    assert commit_receipt.call_args.kwargs["idempotency_key"] == "publish-commit-bld-123"
    register_pending.assert_called_once_with(
        "bld-123",
        "rec-123",
        "test-user",
        "",
        "publish-commit-bld-123",
    )


def test_complete_publish_commit_reuses_pending_idempotency_key():
    pending = {
        "record_id": "rec-123",
        "user_id": "test-user",
        "luks_path": "",
        "idempotency_key": "publish-commit-bld-123",
    }
    publish_result = SimpleNamespace(
        publish_id="pub-123",
        image_id="plain",
        sbom_url="/tmp/sbom.json",
        image_url="docker.io/example/plain",
        log_id=None,
    )

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.workflows.docker_service.get_pending_publish_commit",
        return_value=pending,
    ), patch(
        "tc_api.api.workflows.authenticate_request_identity",
        return_value=SimpleNamespace(user_id="test-user", identity_token="fresh-token"),
    ), patch(
        "tc_api.api.workflows.docker_service.get_publish_status",
        return_value=publish_result,
    ), patch(
        "tc_api.api.workflows.docker_service.commit_and_save_receipt",
        return_value=(True, "rec-committed"),
    ) as commit_receipt, patch(
        "tc_api.api.workflows.docker_service.update_transparencylog_status",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.verify_chain_state",
        return_value="success",
    ), patch(
        "tc_api.api.workflows.docker_service.update_publish_status",
        return_value=None,
    ), patch(
        "tc_api.api.workflows.docker_service.clear_pending_publish_commit",
        return_value=None,
    ):
        with TestClient(app) as client:
            response = client.post(
                "/api/publish-package/commit/bld-123",
                headers={"Authorization": "Bearer fresh-token"},
            )

    assert response.status_code == 200
    assert commit_receipt.call_args.kwargs["idempotency_key"] == "publish-commit-bld-123"


def test_create_luks_rejects_missing_identity_token():
    payload = {
        "user_id": "test-user",
        "passwd": "/root/luks-key",
        "vfs_path": str(Path(LUKS_VFS_BASE_DIR).resolve() / "test-user.img"),
        "vfs_size": "1G",
    }

    class DummyTrustedLog:
        def init_record(self):
            return SimpleNamespace(record_id="rec-123")

        def add_entry(self, *args, **kwargs):
            return None

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.luks_support.docker_service.create_luks_block",
        return_value=("/dev/mapper/test-user", "/dev/loop0"),
    ), patch(
        "tc_api.api.luks_support.docker_service.commit_and_save_receipt"
    ) as commit_receipt, patch(
        "tc_api.api.luks_support.docker_service.verify_chain_state"
    ) as verify_chain_state, patch(
        "tc_api.api.luks_support.docker_service.update_luks_status"
    ) as update_luks_status:
        with TestClient(app) as client:
            client.app.state.trusted_log = DummyTrustedLog()
            response = client.post("/api/create_luks", json=payload)

    assert response.status_code == 400
    assert response.json()["detail"]["operation"] == "create_luks"
    commit_receipt.assert_not_called()
    verify_chain_state.assert_not_called()
    update_luks_status.assert_not_called()


def test_create_luks_rejects_vfs_path_outside_allowed_directory():
    payload = {
        "user_id": "test-user",
        "passwd": "secret-passphrase",
        "vfs_path": "/etc/shadow",
        "vfs_size": "1G",
        "identity_token": "header.payload.signature",
    }

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "test-user",
            "subject": "test-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "test-user",
        },
    ):
        with TestClient(app) as client:
            response = client.post("/api/create_luks", json=payload)

    assert response.status_code == 422
    assert "vfs_path" in response.text


def test_luks_result_allows_unauthenticated_reads():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.luks_support.docker_service.get_luks_status",
        return_value={
            "user_id": "test-user",
            "status": "success",
            "mapper_dir": "mapper-test-user",
            "loop_device": "/dev/loop0",
            "vfs_path": str(Path(LUKS_VFS_BASE_DIR).resolve() / "test-user.img"),
        },
    ):
        with TestClient(app) as client:
            response = client.get("/api/luks-result/test-user")

    assert response.status_code == 200
    assert response.json()["user_id"] == "test-user"


def test_luks_result_ignores_reader_identity_headers():
    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.luks_support.docker_service.get_luks_status",
        return_value={
            "user_id": "alice@example.com",
            "status": "success",
            "mapper_dir": "mapper-alice",
            "loop_device": "/dev/loop0",
            "vfs_path": str(Path(LUKS_VFS_BASE_DIR).resolve() / "alice.img"),
        },
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "alice@example.com",
            "subject": "alice@example.com",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "alice@example.com",
        },
    ):
        with TestClient(app) as client:
            response = client.get(
                "/api/luks-result/alice@example.com",
                headers={"Authorization": "Bearer reader-token"},
            )

    assert response.status_code == 200
    assert response.json()["user_id"] == "alice@example.com"


def test_build_package_rejects_payloads_over_limit():
    oversized = "A" * (BUILD_PACKAGE_MAX_REQUEST_BYTES + 1)

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None):
        with TestClient(app) as client:
            response = client.post(
                "/api/build-package",
                data=oversized,
                headers={
                    "content-type": "application/json",
                    "content-length": str(len(oversized)),
                },
            )

    assert response.status_code == 413


def test_launch_request_rejects_unapproved_registry_host():
    with pytest.raises(ValidationError, match="registry '10.1.2.3' is not allowed"):
        LaunchRequest(
            image_id="svc-image",
            user_id="alice",
            image_url="docker://10.1.2.3/private/image:latest",
        )


def test_publish_request_rejects_non_oci_image_id():
    with pytest.raises(ValidationError, match="image_id must use the oci: transport"):
        PublishPackageRequest(
            build_id="bld-123",
            sbom_url="/tmp/sbom.json",
            image_id="private-image",
            user_id="alice",
        )


def test_get_transparency_request_rejects_path_traversal_ids():
    with pytest.raises(ValidationError, match="build_id must contain only letters, numbers, and dashes"):
        GetTransparencyRequest(build_id="../../tmp/evil", launch_id="launch-123")


def test_build_package_accepts_missing_app_binary():
    token = "header.payload.signature"
    payload = {
        "dockerfile": "FROM busybox\nCMD [\"sh\", \"-c\", \"echo ok\"]\n",
        "encrypt": False,
        "user_id": "test-user",
        "identity_token": token,
    }

    fake_ctx = SimpleNamespace(record_id="rec-123")

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "sigstore.oidc.Issuer.production"
    ) as mock_production, patch(
        "tc_api.api.workflows.build_container_async",
        return_value=None,
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "test-user",
            "subject": "test-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "test-user",
        },
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


def test_build_package_derives_owner_from_identity_token_when_user_id_differs():
    token = "header.payload.signature"
    payload = {
        "dockerfile": "FROM busybox\nCMD [\"sh\", \"-c\", \"echo ok\"]\n",
        "encrypt": False,
        "user_id": "bob@example.com",
        "identity_token": token,
    }

    with patch("tc_api.transparency.commit_client.TrustedLogAPI.init_chain", return_value=None), patch(
        "tc_api.api.workflows.build_container_sync",
        return_value={"success": True, "transparencyLog_verify": "success"},
    ), patch(
        "tc_api.api.workflows.docker_service.generate_uuid",
        return_value="bld-123",
    ), patch(
        "tc_api.api.workflows.docker_service.update_build_status",
        return_value=None,
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "alice@example.com",
            "subject": "alice@example.com",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "alice@example.com",
        },
    ):
        with TestClient(app) as client:
            response = client.post("/api/build-package", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["build_id"] == "bld-123"
    assert data["user_id"] == "alice@example.com"



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
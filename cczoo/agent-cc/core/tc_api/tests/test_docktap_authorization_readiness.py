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
import json
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from tc_api.api.delegation_support import (
    DocktapAuthorizationRequest,
    docktap_authorization_ready,
)
from tc_api.docktap.config import delegation_scope
from tc_api.docktap.preflight import ensure_docktap_authorization


DEFAULT_CHAIN_ID = "default"


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def test_service_default_scope_can_be_overridden_with_env():
    with patch.dict("os.environ", {"DOCKTAP_DELEGATION_SCOPE": "pull,create"}, clear=False):
        assert delegation_scope() == ["pull", "create"]


def test_service_default_scope_falls_back_when_invalid():
    with patch.dict("os.environ", {"DOCKTAP_DELEGATION_SCOPE": "pull,invalid"}, clear=False):
        assert delegation_scope() == ["pull", "create", "start", "stop", "rm"]


def test_explicit_mode_returns_existing_delegation_when_policy_is_satisfied():
    delegation = {
        "delegation_id": "del-existing",
        "scope": ["pull", "create", "start", "stop", "rm"],
        "expires_at": "2099-01-01T00:00:00+00:00",
    }

    with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), patch(
        "tc_api.trucon.database.get_active_delegation",
        return_value=delegation,
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "docktap-user",
            "subject": "docktap-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "docktap-user",
        },
    ):
        response = asyncio.run(docktap_authorization_ready(DocktapAuthorizationRequest(chain_id=DEFAULT_CHAIN_ID, identity_token="token-123")))

    assert response.ready is True
    assert response.source == "existing_delegation"
    assert response.delegation_id == "del-existing"


def test_explicit_mode_creates_delegation_with_service_defaults_when_needed():
    created = {
        "delegation_id": "del-created",
        "expires_at": "2099-01-01T00:00:00+00:00",
        "chain_id": DEFAULT_CHAIN_ID,
        "scope": ["pull", "create", "start", "stop", "rm"],
    }

    with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), patch(
        "tc_api.trucon.database.get_active_delegation",
        return_value=None,
    ), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "docktap-user",
            "subject": "docktap-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "docktap-user",
        },
    ), patch(
        "tc_api.docktap.trucon_client.TruConCommitter.submit_delegation",
        return_value=created,
    ) as submit_mock:
        response = asyncio.run(docktap_authorization_ready(DocktapAuthorizationRequest(chain_id=DEFAULT_CHAIN_ID, identity_token="token-123")))

    assert response.ready is True
    assert response.source == "created_delegation"
    submit_mock.assert_called_once_with(
        chain_id=DEFAULT_CHAIN_ID,
        identity_token_str="token-123",
        scope=None,
        ttl_seconds=None,
    )


def test_explicit_mode_rejects_missing_token_before_readiness_check():
    with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False), patch(
        "tc_api.trucon.database.get_active_delegation",
        return_value=None,
    ):
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(docktap_authorization_ready(DocktapAuthorizationRequest(chain_id=DEFAULT_CHAIN_ID)))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["operation"] == "docktap_authorize"


def test_delegation_disabled_mode_uses_token_readiness():
    with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), patch(
        "tc_api.api.request_auth.inspect_identity_token",
        return_value={
            "valid_for_sigstore": True,
            "errors": [],
            "derived_identity": "docktap-user",
            "subject": "docktap-user",
            "issuer": "https://oauth2.sigstore.dev/auth",
            "email": "docktap-user",
        },
    ):
        response = asyncio.run(docktap_authorization_ready(DocktapAuthorizationRequest(chain_id=DEFAULT_CHAIN_ID, identity_token="token-123")))

    assert response.ready is True
    assert response.source == "identity_token"


def test_preflight_helper_returns_ready_summary():
    captured = {}

    def _urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response({"ready": True, "chain_id": DEFAULT_CHAIN_ID, "source": "created_delegation"})

    with patch("tc_api.docktap.preflight.urllib.request.urlopen", side_effect=_urlopen):
        summary = ensure_docktap_authorization("http://127.0.0.1:8000", DEFAULT_CHAIN_ID, identity_token="token-123")

    assert summary["ready"] is True
    assert captured == {
        "url": "http://127.0.0.1:8000/api/docktap/authorize",
        "body": {"chain_id": DEFAULT_CHAIN_ID, "identity_token": "token-123"},
        "timeout": 30.0,
    }


def test_preflight_helper_raises_when_authorization_is_not_ready():
    with patch(
        "tc_api.docktap.preflight.urllib.request.urlopen",
        return_value=_Response({"ready": False, "source": "missing_identity_token", "detail": "log in first"}),
    ):
        try:
            ensure_docktap_authorization("http://127.0.0.1:8000", DEFAULT_CHAIN_ID, identity_token="token-123")
        except RuntimeError as exc:
            assert "log in first" in str(exc)
        else:
            raise AssertionError("expected RuntimeError when readiness is not satisfied")
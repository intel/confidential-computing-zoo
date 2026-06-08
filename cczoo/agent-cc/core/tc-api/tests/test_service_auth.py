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

"""
Unit tests for TruCon service authentication middleware.

Covers: valid token, missing header, wrong scheme, invalid token,
dev-mode bypass, and startup guard.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Import the app under TRUCON_AUTH_DISABLED=true (set by run_tests.sh / env).
# Tests then patch module-level variables to test specific auth scenarios.
from tc_api.trucon.app import app

TEST_TOKEN = "test-secret-token-1234567890abcdef"
MOD = "tc_api.trucon.app"


# ---------------------------------------------------------------------------
# Tests: auth enforcement
# ---------------------------------------------------------------------------

class TestAuthEnforcement:
    """Middleware rejects requests when auth is enabled and token is required."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        with patch(f"{MOD}._AUTH_DISABLED", False), \
             patch(f"{MOD}._SERVICE_TOKEN", TEST_TOKEN), \
             patch(f"{MOD}._TRUCON_UDS_PATH", ""):
            self.client = TestClient(app, raise_server_exceptions=False)
            yield

    def test_valid_token_accepted(self):
        resp = self.client.get(
            "/status",
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        assert resp.status_code == 200

    def test_missing_authorization_header(self):
        resp = self.client.get("/status")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing Authorization header"

    def test_wrong_authorization_scheme(self):
        resp = self.client.get(
            "/status",
            headers={"Authorization": "Basic dXNlcjpwYXNz"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid Authorization scheme, expected Bearer"

    def test_invalid_token_value(self):
        resp = self.client.get(
            "/status",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid service token"

    def test_commit_endpoint_requires_auth(self):
        resp = self.client.post(
            "/commit",
            json={
                "bundle": "{}",
                "chain_id": "default",
                "event_digest": "sha384:aaa",
                "event_id": "evt-test",
            },
        )
        assert resp.status_code == 401

    def test_commit_endpoint_with_valid_token(self):
        resp = self.client.post(
            "/commit",
            json={
                "bundle": "{}",
                "chain_id": "auth-test",
                "event_digest": "sha384:aaa",
                "event_id": "evt-auth-test",
            },
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        )
        # Should not be 401 — may be 200 or 500 depending on backend,
        # but the auth layer is satisfied.
        assert resp.status_code != 401

    def test_docktap_http_compat_restricted_from_status(self):
        resp = self.client.get(
            "/status",
            headers={
                "Authorization": f"Bearer {TEST_TOKEN}",
                "X-TruCon-Caller-Service": "docktap",
            },
        )
        assert resp.status_code == 403
        assert "not authorized" in resp.json()["detail"]

    def test_docktap_http_compat_can_commit(self):
        resp = self.client.post(
            "/commit",
            json={
                "bundle": "{}",
                "chain_id": "auth-test",
                "event_digest": "sha384:aaa",
                "event_id": "evt-auth-test",
            },
            headers={
                "Authorization": f"Bearer {TEST_TOKEN}",
                "X-TruCon-Caller-Service": "docktap",
            },
        )
        assert resp.status_code != 401
        assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Tests: dev-mode bypass
# ---------------------------------------------------------------------------

class TestDevModeBypass:
    """When auth is disabled, all requests pass without token."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        with patch(f"{MOD}._AUTH_DISABLED", True), \
             patch(f"{MOD}._SERVICE_TOKEN", ""), \
             patch(f"{MOD}._TRUCON_UDS_PATH", ""):
            self.client = TestClient(app, raise_server_exceptions=False)
            yield

    def test_request_without_token_accepted(self):
        resp = self.client.get("/status")
        assert resp.status_code == 200

    def test_request_with_wrong_token_accepted(self):
        resp = self.client.get(
            "/status",
            headers={"Authorization": "Bearer garbage"},
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Tests: startup guard
# ---------------------------------------------------------------------------

class TestStartupGuard:
    """TruCon startup behavior when auth config is incomplete."""

    def test_startup_rejects_without_token(self):
        with patch(f"{MOD}._AUTH_DISABLED", False), \
             patch(f"{MOD}._SERVICE_TOKEN", ""), \
             patch(f"{MOD}._TRUCON_UDS_PATH", ""):
            with pytest.raises(RuntimeError, match="Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH"):
                with TestClient(app):
                    pass

    def test_startup_allows_uds_without_token(self):
        with patch(f"{MOD}._AUTH_DISABLED", False), \
             patch(f"{MOD}._SERVICE_TOKEN", ""), \
             patch(f"{MOD}._TRUCON_UDS_PATH", "/tmp/test-trucon.sock"), \
             patch(f"{MOD}.TruConUnixSocketGateway.start"), \
             patch(f"{MOD}.TruConUnixSocketGateway.stop"):
            with TestClient(app):
                pass

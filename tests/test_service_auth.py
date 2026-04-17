"""
Unit tests for TruCon service authentication middleware.

Covers: valid token, missing header, wrong scheme, invalid token,
dev-mode bypass, and startup guard.
"""

import os
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
             patch(f"{MOD}._SERVICE_TOKEN", TEST_TOKEN):
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


# ---------------------------------------------------------------------------
# Tests: dev-mode bypass
# ---------------------------------------------------------------------------

class TestDevModeBypass:
    """When auth is disabled, all requests pass without token."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        with patch(f"{MOD}._AUTH_DISABLED", True), \
             patch(f"{MOD}._SERVICE_TOKEN", ""):
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
    """TruCon refuses to start when auth is enabled but token is empty."""

    def test_startup_exits_without_token(self):
        """Lifespan should raise RuntimeError when _AUTH_DISABLED=False and _SERVICE_TOKEN=''."""
        with patch(f"{MOD}._AUTH_DISABLED", False), \
             patch(f"{MOD}._SERVICE_TOKEN", ""):
            with pytest.raises(RuntimeError, match="TRUCON_SERVICE_TOKEN is not set"):
                with TestClient(app):
                    pass

import base64
import json
from datetime import datetime, timedelta, timezone

from tc_api.oidc_preflight import inspect_identity_token


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def test_preflight_accepts_github_actions_style_token():
    now = datetime.now(timezone.utc)
    token = _jwt(
        {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "sigstore",
            "sub": "repo:example/project:ref:refs/heads/main",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        }
    )

    result = inspect_identity_token(
        token,
        expected_identity="repo:example/project:ref:refs/heads/main",
    )

    assert result["valid_for_sigstore"] is True
    assert result["derived_identity"] == "repo:example/project:ref:refs/heads/main"
    assert result["identity_matches_expected"] is True
    assert result["errors"] == []


def test_preflight_rejects_wrong_audience():
    now = datetime.now(timezone.utc)
    token = _jwt(
        {
            "iss": "https://token.actions.githubusercontent.com",
            "aud": "not-sigstore",
            "sub": "repo:example/project:ref:refs/heads/main",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        }
    )

    result = inspect_identity_token(token)

    assert result["valid_for_sigstore"] is False
    assert any("audience does not include 'sigstore'" in error for error in result["errors"])


def test_preflight_uses_email_for_known_email_issuer():
    now = datetime.now(timezone.utc)
    token = _jwt(
        {
            "iss": "https://accounts.google.com",
            "aud": "sigstore",
            "sub": "opaque-google-subject",
            "email": "alice@example.com",
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=10)).timestamp()),
        }
    )

    result = inspect_identity_token(token, expected_identity="alice@example.com")

    assert result["valid_for_sigstore"] is True
    assert result["derived_identity"] == "alice@example.com"
    assert result["known_issuer_identity_claim"] == "email"
import base64
import json

from tc_api import sigstore_identity


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def test_resolve_sigstore_identity_token_respects_min_ttl_override(tmp_path, monkeypatch):
    cache_path = tmp_path / "sigstore-token.json"
    token = _jwt({"exp": 1_777_431_615})

    monkeypatch.setenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_CACHE_ENV, str(cache_path))
    monkeypatch.delenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_MIN_TTL_ENV, raising=False)
    monkeypatch.delenv(sigstore_identity.SIGSTORE_INTERACTIVE_LOGIN_ENV, raising=False)
    monkeypatch.setattr(sigstore_identity.time, "time", lambda: 1_777_431_602)

    sigstore_identity.cache_sigstore_identity_token(token)

    assert sigstore_identity.resolve_sigstore_identity_token(
        "publish",
        allow_interactive=False,
    ) is None
    assert (
        sigstore_identity.resolve_sigstore_identity_token(
            "publish",
            allow_interactive=False,
            min_ttl_seconds=0,
        )
        == token
    )
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
from types import SimpleNamespace

import pytest

from tc_api.identity import sigstore_identity


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


def test_resolve_sigstore_identity_token_force_refresh_skips_cached_token(tmp_path, monkeypatch):
    cache_path = tmp_path / "sigstore-token.json"
    cached_token = _jwt({"exp": 1_777_431_900, "sub": "cached"})
    fresh_token = _jwt({"exp": 1_777_432_500, "sub": "fresh"})

    monkeypatch.setenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_CACHE_ENV, str(cache_path))
    monkeypatch.delenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(sigstore_identity.SIGSTORE_INTERACTIVE_LOGIN_ENV, raising=False)
    monkeypatch.setattr(sigstore_identity.time, "time", lambda: 1_777_431_602)
    monkeypatch.setattr(sigstore_identity.sys, "stdin", SimpleNamespace(isatty=lambda: True))
    monkeypatch.setattr(sigstore_identity.sys, "stdout", SimpleNamespace(isatty=lambda: True))

    sigstore_identity.cache_sigstore_identity_token(cached_token)

    from tc_api.cli import oidc_verification_code

    monkeypatch.setattr(
        oidc_verification_code,
        "acquire_sigstore_token_via_oob",
        lambda operation, cache_token=True: fresh_token,
    )

    assert sigstore_identity.resolve_sigstore_identity_token(
        "baseline",
        allow_interactive=True,
        force_refresh=True,
    ) == fresh_token


def test_resolve_sigstore_identity_token_rejects_interactive_refresh_without_tty(monkeypatch):
    monkeypatch.delenv(sigstore_identity.SIGSTORE_IDENTITY_TOKEN_ENV, raising=False)
    monkeypatch.delenv(sigstore_identity.SIGSTORE_INTERACTIVE_LOGIN_ENV, raising=False)
    monkeypatch.setattr(sigstore_identity, "_MEMORY_TOKEN", None)
    monkeypatch.setattr(sigstore_identity, "_MEMORY_EXPIRY", None)
    monkeypatch.setattr(sigstore_identity, "_load_cached_token_from_disk", lambda: None)
    monkeypatch.setattr(sigstore_identity.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(sigstore_identity.sys, "stdout", SimpleNamespace(isatty=lambda: False))

    with pytest.raises(sigstore_identity.MissingSigstoreIdentityTokenError, match="client-side challenge flow"):
        sigstore_identity.resolve_sigstore_identity_token(
            "build",
            allow_interactive=True,
            require_token=True,
        )
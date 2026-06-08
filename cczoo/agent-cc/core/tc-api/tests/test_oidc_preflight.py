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
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from tc_api.identity import oidc_preflight


def _make_token(**claims):
    now = int(datetime.now(timezone.utc).timestamp())
    base_claims = {
        "iss": "https://token.actions.githubusercontent.com",
        "aud": "sigstore",
        "sub": "repo:example/project:ref:refs/heads/main",
        "iat": now,
        "exp": now + 60,
    }
    base_claims.update(claims)
    return _jwt(base_claims)


def _jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def enc(obj):
        raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{enc(header)}.{enc(payload)}.sig"


def test_inspect_identity_token_rejects_expired_token(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)

    result = oidc_preflight.inspect_identity_token(
        _make_token(iat=now - 100, exp=now - 40),
        expected_identity="repo:example/project:ref:refs/heads/main",
    )

    assert result["valid_for_sigstore"] is False
    assert "Token has already expired." in result["errors"]
    assert result["expires_in_seconds"] == -40


def test_main_fetch_and_run_real_rekor_smoke(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now, exp=now + 300)
    calls = {}

    class DummyIssuer:
        def identity_token(self, client_id="sigstore", client_secret="", force_oob=False):
            calls["fetch"] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "force_oob": force_oob,
            }
            return token

    monkeypatch.setattr(oidc_preflight.Issuer, "production", staticmethod(lambda: DummyIssuer()))
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)

    def fake_run(command, env, check):
        calls["run"] = {
            "command": command,
            "env": env,
            "check": check,
        }
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(oidc_preflight.subprocess, "run", fake_run)

    rc = oidc_preflight.main([
        "--fetch",
        "--force-oob",
        "--run-real-rekor-smoke",
        "--pytest-args",
        "-q",
        "-k",
        "multi_chain",
    ])

    assert rc == 0
    assert calls["fetch"] == {
        "client_id": "sigstore",
        "client_secret": "",
        "force_oob": True,
    }
    assert calls["run"]["command"] == [
        oidc_preflight.sys.executable,
        "-m",
        "pytest",
        "tests/test_real_rekor_integration.py",
        "-q",
        "-k",
        "multi_chain",
    ]
    assert calls["run"]["env"]["TC_API_RUN_REAL_REKOR_TESTS"] == "1"
    assert calls["run"]["env"][oidc_preflight.DEFAULT_TOKEN_ENV] == token
    assert calls["run"]["check"] is False


def test_fetch_opens_browser_via_helper(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now, exp=now + 300)
    calls = {}

    class DummyIssuer:
        def identity_token(self, client_id="sigstore", client_secret="", force_oob=False):
            calls["force_oob"] = force_oob
            oidc_preflight.sigstore_oidc.webbrowser.open("http://localhost:12345")
            return token

    monkeypatch.setattr(oidc_preflight.Issuer, "production", staticmethod(lambda: DummyIssuer()))
    monkeypatch.setattr(oidc_preflight, "_open_login_browser", lambda url: calls.setdefault("browser_url", url) or True)

    fetched = oidc_preflight._fetch_token(
        SimpleNamespace(oidc_client_id="sigstore", oidc_client_secret="", force_oob=False)
    )

    assert fetched == token
    assert calls["force_oob"] is False
    assert calls["browser_url"] == "http://localhost:12345"


def test_fetch_force_oob_skips_browser_helper(monkeypatch):
    token = _make_token()
    calls = {"browser_called": False}

    class DummyIssuer:
        def identity_token(self, client_id="sigstore", client_secret="", force_oob=False):
            calls["force_oob"] = force_oob
            return token

    monkeypatch.setattr(oidc_preflight.Issuer, "production", staticmethod(lambda: DummyIssuer()))
    monkeypatch.setattr(oidc_preflight, "_open_login_browser", lambda url: calls.__setitem__("browser_called", True))

    fetched = oidc_preflight._fetch_token(
        SimpleNamespace(oidc_client_id="sigstore", oidc_client_secret="", force_oob=True)
    )

    assert fetched == token
    assert calls["force_oob"] is True
    assert calls["browser_called"] is False


def test_main_fetch_and_run_real_rekor_oci_multi_chain_smoke(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now, exp=now + 300)
    calls = {}

    class DummyIssuer:
        def identity_token(self, client_id="sigstore", client_secret="", force_oob=False):
            calls["fetch"] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "force_oob": force_oob,
            }
            return token

    monkeypatch.setattr(oidc_preflight.Issuer, "production", staticmethod(lambda: DummyIssuer()))
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)

    def fake_run(command, env, check):
        calls["run"] = {
            "command": command,
            "env": env,
            "check": check,
        }
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(oidc_preflight.subprocess, "run", fake_run)

    rc = oidc_preflight.main([
        "--fetch",
        "--run-real-rekor-oci-multi-chain-smoke",
    ])

    assert rc == 0
    assert calls["run"]["command"] == [
        oidc_preflight.sys.executable,
        "-m",
        "pytest",
        oidc_preflight.DEFAULT_REAL_REKOR_OCI_MULTI_CHAIN_TEST,
        "-q",
    ]
    assert calls["run"]["env"]["TC_API_RUN_REAL_REKOR_TESTS"] == "1"
    assert calls["run"]["env"]["TC_API_RUN_REAL_OCI_MIRROR_TESTS"] == "1"
    assert calls["run"]["env"][oidc_preflight.DEFAULT_TOKEN_ENV] == token
    assert calls["run"]["check"] is False


def test_main_does_not_run_smoke_when_preflight_fails(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now - 100, exp=now - 5)
    ran = {"smoke": False}

    class DummyIssuer:
        def identity_token(self, client_id="sigstore", client_secret="", force_oob=False):
            return token

    monkeypatch.setattr(oidc_preflight.Issuer, "production", staticmethod(lambda: DummyIssuer()))
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)

    def fake_run(command, env, check):
        ran["smoke"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(oidc_preflight.subprocess, "run", fake_run)

    rc = oidc_preflight.main(["--fetch", "--run-real-rekor-smoke"])

    assert rc == 1
    assert ran["smoke"] is False


def test_load_token_from_interactive_prompt(monkeypatch):
    token = _make_token()
    monkeypatch.setattr(oidc_preflight.getpass, "getpass", lambda _prompt: token)

    loaded = oidc_preflight._load_token(
        SimpleNamespace(prompt_token=True, stdin=False, env_var=oidc_preflight.DEFAULT_TOKEN_ENV)
    )

    assert loaded == token


def test_main_uses_interactive_prompt_token(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now, exp=now + 300)
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)
    monkeypatch.setattr(oidc_preflight.getpass, "getpass", lambda _prompt: token)

    rc = oidc_preflight.main(["--prompt-token", "--json"])

    assert rc == 0


def test_load_expected_identity_from_interactive_prompt(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _prompt: "alice@example.com")

    expected_identity = oidc_preflight._load_expected_identity(
        SimpleNamespace(expected_identity=None, prompt_expected_identity=True)
    )

    assert expected_identity == "alice@example.com"


def test_main_uses_interactive_expected_identity(monkeypatch):
    now = int(datetime.now(timezone.utc).timestamp())
    token = _make_token(iat=now, exp=now + 300)
    monkeypatch.setattr(oidc_preflight, "_utc_now_epoch", lambda: now)
    monkeypatch.setattr(oidc_preflight.getpass, "getpass", lambda _prompt: token)
    monkeypatch.setattr("builtins.input", lambda _prompt: "repo:example/project:ref:refs/heads/main")

    rc = oidc_preflight.main(["--prompt-token", "--prompt-expected-identity", "--json"])

    assert rc == 0


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

    result = oidc_preflight.inspect_identity_token(
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

    result = oidc_preflight.inspect_identity_token(token)

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

    result = oidc_preflight.inspect_identity_token(token, expected_identity="alice@example.com")

    assert result["valid_for_sigstore"] is True
    assert result["derived_identity"] == "alice@example.com"
    assert result["known_issuer_identity_claim"] == "email"
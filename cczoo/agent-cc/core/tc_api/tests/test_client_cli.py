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

import json

import pytest

from tc_api.cli import client as client_mod


class FakeResponse:
    def __init__(self, status_code, data):
        self.status_code = status_code
        self.data = data

    @property
    def ok(self):
        return 200 <= self.status_code < 300


def test_build_command_retries_after_sigstore_login(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "open_in_browser_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                    }
                },
            )
        if len(calls) == 2:
            assert method == "GET"
            assert path == "/api/sigstore/login-status/sess-123"
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        assert payload["identity_token"] == "token-123"
        return FakeResponse(200, {"build_id": "bld-123", "status": "submitted"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "--base-url",
        "http://localhost:8000",
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"build_id": "bld-123"' in captured.out
    assert "Open this browser page and finish login there" in captured.err
    assert "points at localhost" in captured.err


def test_build_command_retries_via_resume_path_after_sigstore_login(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                        "retry_method": "POST",
                        "retry_path": "/api/build-package/commit/bld-123",
                        "build_id": "bld-123",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls[2] == (
        "POST",
        "/api/build-package/commit/bld-123",
        {"identity_token": "token-123"},
        None,
    )
    assert '"status": "success"' in captured.out


def test_build_command_handles_second_sigstore_challenge_for_commit_resume(monkeypatch, capsys):
    calls = []
    issued_tokens = iter(["token-1", "token-2"])

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-1",
                        "session_id": "sess-1",
                        "login_status_url": "/api/sigstore/login-status/sess-1",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-2",
                        "session_id": "sess-2",
                        "login_status_url": "/api/sigstore/login-status/sess-2",
                        "retry_method": "POST",
                        "retry_path": "/api/build-package/commit/bld-123",
                        "build_id": "bld-123",
                    }
                },
            )
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_oob", lambda operation="docktap": next(issued_tokens))

    rc = client_mod.main([
        "--sigstore-login",
        "oob",
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [
        ("POST", "/api/build-package", {"dockerfile": "FROM busybox", "user_id": "alice"}, None),
        ("POST", "/api/build-package", {"dockerfile": "FROM busybox", "user_id": "alice", "identity_token": "token-1"}, None),
        ("POST", "/api/build-package/commit/bld-123", {"identity_token": "token-2"}, None),
    ]
    assert '"status": "success"' in captured.out


def test_build_command_rewrites_browser_url(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"build_id": "bld-123", "status": "submitted"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "--browser-base-url",
        "http://10.0.0.8:8000",
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert "http://10.0.0.8:8000/api/sigstore/interactive-login?operation=build&session_id=sess-123" in captured.err
    assert "points at localhost" not in captured.err


def test_build_command_auto_falls_back_to_oob(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                    }
                },
            )
        assert payload["identity_token"] == "token-xyz"
        return FakeResponse(200, {"build_id": "bld-123", "status": "submitted"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_oob", lambda operation="docktap": "token-xyz")

    rc = client_mod.main([
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"build_id": "bld-123"' in captured.out
    assert len(calls) == 2
    assert calls[1][0] == "POST"


def test_build_command_handles_two_sigstore_challenges_with_oob(monkeypatch, capsys):
    calls = []
    issued_tokens = iter(["token-one", "token-two"])

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-1",
                        "session_id": "sess-1",
                        "login_status_url": "/api/sigstore/login-status/sess-1",
                    }
                },
            )
        if len(calls) == 2:
            assert payload["identity_token"] == "token-one"
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build.",
                        "operation": "build",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build&session_id=sess-2",
                        "session_id": "sess-2",
                        "login_status_url": "/api/sigstore/login-status/sess-2",
                        "retry_method": "POST",
                        "retry_path": "/api/build-package/commit/bld-123",
                        "build_id": "bld-123",
                    }
                },
            )
        assert calls[2] == (
            "POST",
            "/api/build-package/commit/bld-123",
            {"identity_token": "token-two"},
            None,
        )
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_oob", lambda operation="docktap": next(issued_tokens))

    rc = client_mod.main([
        "--sigstore-login",
        "oob",
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"status": "success"' in captured.out


def test_build_result_command_fetches_expected_path(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: "cached-token")

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["build-result", "bld-123"])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(
        "GET",
        "/api/build-result/bld-123",
        None,
        {"Authorization": "Bearer cached-token"},
    )]
    assert '"status": "success"' in captured.out


def test_luks_result_command_fetches_expected_path(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: "cached-token")

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        return FakeResponse(200, {"user_id": "alice@example.com", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["luks-result", "alice@example.com"])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(
        "GET",
        "/api/luks-result/alice@example.com",
        None,
        {"Authorization": "Bearer cached-token"},
    )]
    assert '"status": "success"' in captured.out


def test_build_result_command_retries_with_authorization_header(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: None)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                400,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for build_result.",
                        "operation": "build_result",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=build_result&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["--sigstore-login", "server-session", "build-result", "bld-123"])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls[0] == ("GET", "/api/build-result/bld-123", None, None)
    assert calls[2] == (
        "GET",
        "/api/build-result/bld-123",
        None,
        {"Authorization": "Bearer token-123"},
    )
    assert '"status": "success"' in captured.out


def test_launch_result_command_retries_via_resume_path_with_authorization_header(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: None)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for launch.",
                        "operation": "launch",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=launch&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                        "retry_method": "POST",
                        "retry_path": "/api/deploy-launch/commit/launch-123",
                        "launch_id": "launch-123",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"launch_id": "launch-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["--sigstore-login", "server-session", "launch-result", "launch-123"])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls[2] == (
        "POST",
        "/api/deploy-launch/commit/launch-123",
        None,
        {"Authorization": "Bearer token-123"},
    )
    assert '"status": "success"' in captured.out


def test_publish_command_retries_via_resume_path_after_sigstore_login(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for publish.",
                        "operation": "publish",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=publish&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                        "retry_method": "POST",
                        "retry_path": "/api/publish-package/commit/bld-123",
                        "build_id": "bld-123",
                    }
                },
            )
        if len(calls) == 2:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "publish",
        "--payload-json",
        json.dumps({"build_id": "bld-123", "user_id": "alice", "image_id": "oci:/tmp/plain", "sbom_url": "/tmp/sbom.json"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls[2] == (
        "POST",
        "/api/publish-package/commit/bld-123",
        {"identity_token": "token-123"},
        None,
    )
    assert '"status": "success"' in captured.out


def test_publish_command_reads_payload_file(monkeypatch, tmp_path, capsys):
    payload_path = tmp_path / "publish.json"
    payload_path.write_text(json.dumps({"build_id": "bld-123", "user_id": "alice"}), encoding="utf-8")

    def fake_request_json(self, method, path, payload=None, headers=None):
        assert method == "POST"
        assert path == "/api/publish-package"
        assert payload == {"build_id": "bld-123", "user_id": "alice"}
        return FakeResponse(200, {"publish_id": "pub-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["publish", "--payload-file", str(payload_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"publish_id": "pub-123"' in captured.out


def test_deploy_command_polls_launch_result_until_success(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: "cached-token")
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(200, {"launch_id": "launch-123", "status": "initiated"})
        if len(calls) == 2:
            return FakeResponse(200, {"launch_id": "launch-123", "status": "launching"})
        return FakeResponse(200, {"launch_id": "launch-123", "status": "success", "instance_ids": ["ctr-1"]})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main([
        "deploy",
        "--payload-json",
        json.dumps({"image_id": "img-123", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [
        ("POST", "/api/deploy-launch", {"image_id": "img-123", "user_id": "alice"}, None),
        ("GET", "/api/launch-result/launch-123", None, {"Authorization": "Bearer cached-token"}),
        ("GET", "/api/launch-result/launch-123", None, {"Authorization": "Bearer cached-token"}),
    ]
    assert "Deploy accepted as launch launch-123; waiting for launch-result..." in captured.err
    assert "Launch launch-123 status: launching" in captured.err
    assert '"status": "success"' in captured.out


def test_deploy_command_handles_launch_result_sigstore_resume(monkeypatch, capsys):
    calls = []

    monkeypatch.setattr(client_mod, "resolve_sigstore_identity_token", lambda *args, **kwargs: None)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(200, {"launch_id": "launch-123", "status": "initiated"})
        if len(calls) == 2:
            return FakeResponse(
                428,
                {
                    "detail": {
                        "error": "Sigstore identity token is required for launch.",
                        "operation": "launch",
                        "after_login_open_url": "http://localhost:8000/api/sigstore/interactive-login?operation=launch&session_id=sess-123",
                        "session_id": "sess-123",
                        "login_status_url": "/api/sigstore/login-status/sess-123",
                        "retry_method": "POST",
                        "retry_path": "/api/deploy-launch/commit/launch-123",
                        "launch_id": "launch-123",
                    }
                },
            )
        if len(calls) == 3:
            return FakeResponse(200, {"status": "token_ready", "identity_token": "token-123"})
        return FakeResponse(200, {"launch_id": "launch-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "deploy",
        "--payload-json",
        json.dumps({"image_id": "img-123", "user_id": "alice"}),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls[3] == (
        "POST",
        "/api/deploy-launch/commit/launch-123",
        None,
        {"Authorization": "Bearer token-123"},
    )
    assert '"status": "success"' in captured.out


def test_create_luks_command_posts_expected_path(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        return FakeResponse(200, {"user_id": "alice", "mapper_dir": "/dev/mapper/luks-alice"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main([
        "create_luks",
        "--payload-json",
        json.dumps({
            "user_id": "alice",
            "passwd": "secret",
            "vfs_path": "/mnt/luks_fs/alice.img",
            "vfs_size": "8M",
        }),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(
        "POST",
        "/api/create_luks",
        {
            "user_id": "alice",
            "passwd": "secret",
            "vfs_path": "/mnt/luks_fs/alice.img",
            "vfs_size": "8M",
        },
        None,
    )]
    assert '"mapper_dir": "/dev/mapper/luks-alice"' in captured.out


def test_umount_luks_command_posts_expected_path(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        return FakeResponse(200, {"user_id": "alice", "mount_path": "/mnt/luks/alice"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main([
        "umount_luks",
        "--payload-json",
        json.dumps({
            "user_id": "alice",
            "mapper_dir": "/dev/mapper/luks-alice",
            "mount_path": "/mnt/luks/alice",
            "loop_device": "/dev/loop7",
        }),
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [(
        "POST",
        "/api/unmount_luks",
        {
            "user_id": "alice",
            "mapper_dir": "/dev/mapper/luks-alice",
            "mount_path": "/mnt/luks/alice",
            "loop_device": "/dev/loop7",
        },
        None,
    )]
    assert '"mount_path": "/mnt/luks/alice"' in captured.out


def test_client_returns_nonzero_on_server_error(monkeypatch, capsys):
    def fake_request_json(self, method, path, payload=None, headers=None):
        return FakeResponse(500, {"error": "boom"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["transparency-log", "log-123"])

    captured = capsys.readouterr()
    assert rc == 1
    assert '"error": "boom"' in captured.err


def test_build_command_uses_long_running_timeout(monkeypatch, capsys):
    captured = {}

    original_init = client_mod.ApiClient.__init__

    def fake_init(self, base_url, timeout_seconds=client_mod.DEFAULT_TIMEOUT_SECONDS):
        captured["base_url"] = base_url
        captured["timeout_seconds"] = timeout_seconds
        original_init(self, base_url, timeout_seconds=timeout_seconds)

    def fake_request_json(self, method, path, payload=None, headers=None):
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "__init__", fake_init)
    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main([
        "build",
        "--payload-json",
        json.dumps({"dockerfile": "FROM busybox", "user_id": "alice"}),
    ])

    captured_output = capsys.readouterr()
    assert rc == 0
    assert captured["timeout_seconds"] == client_mod.DEFAULT_LONG_TIMEOUT_SECONDS
    assert '"status": "success"' in captured_output.out


def test_sigstore_token_command_returns_json(monkeypatch, capsys):
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_for_cli", lambda *args, **kwargs: "token-xyz")
    monkeypatch.setattr(client_mod, "cache_sigstore_identity_token", lambda token: None)

    rc = client_mod.main(["sigstore-token"])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"identity_token": "token-xyz"' in captured.out


def test_sigstore_token_command_can_print_docktap_export(monkeypatch, capsys):
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_for_cli", lambda *args, **kwargs: "token-xyz")
    monkeypatch.setattr(client_mod, "cache_sigstore_identity_token", lambda token: None)

    rc = client_mod.main([
        "sigstore-token",
        "--format",
        "export",
        "--env-var",
        "DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert 'export DOCKTAP_SIGSTORE_IDENTITY_TOKEN="token-xyz"' in captured.out


def test_run_docktap_command_acquires_token_and_execs_docktap(monkeypatch):
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_for_cli", lambda *args, **kwargs: "token-xyz")
    monkeypatch.setattr(client_mod, "cache_sigstore_identity_token", lambda token: None)
    calls = {}

    def fake_exec(identity_token, *, socket_path, docker_socket_path, debug, env_var):
        calls["identity_token"] = identity_token
        calls["socket_path"] = socket_path
        calls["docker_socket_path"] = docker_socket_path
        calls["debug"] = debug
        calls["env_var"] = env_var
        raise SystemExit(0)

    monkeypatch.setattr(client_mod, "_exec_docktap_with_identity_token", fake_exec)

    with pytest.raises(SystemExit) as exc_info:
        client_mod.main([
            "run-docktap",
            "--socket-path",
            "/var/run/docktap/docker.sock",
            "--docker-socket-path",
            "/var/run/docker.sock",
            "--debug",
        ])

    assert exc_info.value.code == 0
    assert calls == {
        "identity_token": "token-xyz",
        "socket_path": "/var/run/docktap/docker.sock",
        "docker_socket_path": "/var/run/docker.sock",
        "debug": True,
        "env_var": "DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
    }


def test_sigstore_token_command_uses_server_session_flow(monkeypatch, capsys):
    calls = []
    cached = {}

    def fake_request_json(self, method, path, payload=None, headers=None):
        calls.append((method, path, payload, headers))
        if len(calls) == 1:
            return FakeResponse(
                200,
                {
                    "operation": "docktap",
                    "status": "browser_login_pending",
                    "session_id": "sess-456",
                    "interactive_login_url": "http://localhost:8000/api/sigstore/interactive-login?operation=docktap&session_id=sess-456",
                },
            )
        assert method == "GET"
        assert path == "/api/sigstore/login-status/sess-456"
        return FakeResponse(200, {"status": "token_ready", "identity_token": "token-xyz"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)
    monkeypatch.setattr(client_mod.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(client_mod, "cache_sigstore_identity_token", lambda token: cached.setdefault("token", token))

    rc = client_mod.main([
        "--sigstore-login",
        "server-session",
        "sigstore-token",
        "--format",
        "export",
    ])

    captured = capsys.readouterr()
    assert rc == 0
    assert 'export DOCKTAP_SIGSTORE_IDENTITY_TOKEN="token-xyz"' in captured.out
    assert calls[0] == ("GET", "/api/sigstore/identity-token?operation=docktap&flow=server-callback", None, None)
    assert cached["token"] == "token-xyz"


def test_run_docktap_auto_mode_uses_copy_url_session_without_browser_base(monkeypatch):
    start_calls = []

    def fake_start(client, operation, flow):
        start_calls.append((operation, flow))
        return {"status": "token_ready", "identity_token": "token-xyz"}

    def fake_exec(identity_token, *, socket_path, docker_socket_path, debug, env_var):
        raise SystemExit(0)

    monkeypatch.setattr(client_mod, "_start_sigstore_identity_session", fake_start)
    monkeypatch.setattr(client_mod, "_exec_docktap_with_identity_token", fake_exec)
    monkeypatch.setattr(client_mod, "cache_sigstore_identity_token", lambda token: None)

    with pytest.raises(SystemExit) as exc_info:
        client_mod.main(["run-docktap"])

    assert exc_info.value.code == 0
    assert start_calls == [("docktap", "copy-url")]


def test_acquire_sigstore_token_oob_caches_token(monkeypatch):
    calls = {}

    def fake_acquire(*, operation):
        calls["operation"] = operation
        return "token-xyz"

    monkeypatch.setattr(client_mod, "acquire_sigstore_token_via_oob", fake_acquire)

    token = client_mod._acquire_sigstore_token_oob("build")

    assert token == "token-xyz"
    assert calls["operation"] == "build"


def test_exec_docktap_with_identity_token_uses_expected_execvpe(monkeypatch):
    monkeypatch.setattr(client_mod.sys, "executable", "/venv/bin/python")
    monkeypatch.setenv("EXISTING", "1")
    captured = {}

    def fake_execvpe(file, argv, env):
        captured["file"] = file
        captured["argv"] = argv
        captured["env"] = env
        raise SystemExit(0)

    monkeypatch.setattr(client_mod.os, "execvpe", fake_execvpe)

    with pytest.raises(SystemExit) as exc_info:
        client_mod._exec_docktap_with_identity_token(
            "token-xyz",
            socket_path="/tmp/docker-proxy.sock",
            docker_socket_path="/var/run/docker.sock",
            debug=True,
            env_var="DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
        )

    assert exc_info.value.code == 0
    assert captured["file"] == "/venv/bin/python"
    assert captured["argv"] == [
        "/venv/bin/python",
        "-m",
        "tc_api.docktap.main",
        "--socket-path",
        "/tmp/docker-proxy.sock",
        "--docker-socket-path",
        "/var/run/docker.sock",
        "--debug",
    ]
    assert captured["env"]["DOCKTAP_SIGSTORE_IDENTITY_TOKEN"] == "token-xyz"
    assert captured["env"]["EXISTING"] == "1"
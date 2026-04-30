import json

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

    def fake_request_json(self, method, path, payload=None):
        calls.append((method, path, payload))
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


def test_build_command_rewrites_browser_url(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None):
        calls.append((method, path, payload))
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

    def fake_request_json(self, method, path, payload=None):
        calls.append((method, path, payload))
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
    monkeypatch.setattr(client_mod, "_acquire_sigstore_token_oob", lambda: "token-xyz")

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


def test_build_result_command_fetches_expected_path(monkeypatch, capsys):
    calls = []

    def fake_request_json(self, method, path, payload=None):
        calls.append((method, path, payload))
        return FakeResponse(200, {"build_id": "bld-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["build-result", "bld-123"])

    captured = capsys.readouterr()
    assert rc == 0
    assert calls == [("GET", "/api/build-result/bld-123", None)]
    assert '"status": "success"' in captured.out


def test_publish_command_reads_payload_file(monkeypatch, tmp_path, capsys):
    payload_path = tmp_path / "publish.json"
    payload_path.write_text(json.dumps({"build_id": "bld-123", "user_id": "alice"}), encoding="utf-8")

    def fake_request_json(self, method, path, payload=None):
        assert method == "POST"
        assert path == "/api/publish-package"
        assert payload == {"build_id": "bld-123", "user_id": "alice"}
        return FakeResponse(200, {"publish_id": "pub-123", "status": "success"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["publish", "--payload-file", str(payload_path)])

    captured = capsys.readouterr()
    assert rc == 0
    assert '"publish_id": "pub-123"' in captured.out


def test_client_returns_nonzero_on_server_error(monkeypatch, capsys):
    def fake_request_json(self, method, path, payload=None):
        return FakeResponse(500, {"error": "boom"})

    monkeypatch.setattr(client_mod.ApiClient, "request_json", fake_request_json)

    rc = client_mod.main(["transparency-log", "log-123"])

    captured = capsys.readouterr()
    assert rc == 1
    assert '"error": "boom"' in captured.err
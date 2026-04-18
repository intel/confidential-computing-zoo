import json
from unittest.mock import patch

from tc_api.cli.verify import main


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _urlopen_factory(chain_state_payload, verify_payload):
    def _urlopen(request, timeout=15):
        url = request.full_url
        if "/chain-state/" in url:
            return _Response(chain_state_payload)
        if "/verify-chain/" in url:
            return _Response(verify_payload)
        raise AssertionError(f"Unexpected URL: {url}")

    return _urlopen


def test_verify_cli_json_success(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": True,
        "chain_id": "default",
        "total_entries": 1,
        "mr_verified": 1,
        "rekor_confirmed": 1,
        "rekor_pending": 0,
        "rtmr_available": True,
        "head_mr_value": "aa",
        "first_error_at": None,
        "entries": [
            {
                "seq": 1,
                "record_id": "rec-1",
                "event_id": "evt-1",
                "mr_ok": True,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": "aa",
                "prev_log_id_ok": None,
                "error": None,
            }
        ],
    }
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "entry_count": 1,
                "entries": [
                    {
                        "event_id": "evt-1",
                        "signer_identity": "alice@example.com",
                        "digest": "sha384:evt-1",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["summary"]["status"] == "verified"
    assert captured["mode"]["verification_mode"] == "tee"
    assert captured["entries"][0]["event_id"] == "evt-1"


def test_verify_cli_require_tee_fails_in_non_tee_mode(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": True,
        "chain_id": "default",
        "total_entries": 1,
        "mr_verified": 0,
        "rekor_confirmed": 1,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": None,
        "entries": [],
    }
    immutable_result = type("VerifyResult", (), {"success": True, "errors": [], "details": {"entry_count": 1, "entries": []}})()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--json", "--require-tee"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["mode"]["verification_mode"] == "non_tee_fallback"
    assert "TEE evidence was required but unavailable" in captured["errors"]


def test_verify_cli_fail_on_pending(capsys):
    chain_state = {"chain_id": "default", "head_log_id": None}
    trucon_verify = {
        "valid": True,
        "chain_id": "default",
        "total_entries": 2,
        "mr_verified": 0,
        "rekor_confirmed": 1,
        "rekor_pending": 1,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": None,
        "entries": [
            {
                "seq": 1,
                "record_id": "rec-1",
                "event_id": "evt-1",
                "mr_ok": None,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": None,
                "prev_log_id_ok": True,
                "error": None,
            },
            {
                "seq": 2,
                "record_id": "rec-2",
                "event_id": "evt-2",
                "mr_ok": None,
                "rekor_ok": False,
                "rtmr_extended": True,
                "mr_value": None,
                "prev_log_id_ok": None,
                "error": None,
            },
        ],
    }

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        exit_code = main(["default", "--json", "--fail-on-pending"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "failed"
    assert "Pending records present while --fail-on-pending is enabled" in captured["errors"]


def test_verify_cli_human_output_contains_per_record_detail(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": True,
        "chain_id": "default",
        "total_entries": 1,
        "mr_verified": 1,
        "rekor_confirmed": 1,
        "rekor_pending": 0,
        "rtmr_available": True,
        "head_mr_value": "aa",
        "first_error_at": None,
        "entries": [
            {
                "seq": 1,
                "record_id": "rec-1",
                "event_id": "evt-1",
                "mr_ok": True,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": "aa",
                "prev_log_id_ok": None,
                "error": None,
            }
        ],
    }
    immutable_result = type("VerifyResult", (), {"success": True, "errors": [], "details": {"entry_count": 1, "entries": [{"event_id": "evt-1"}]}})()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Per-record detail:" in output
    assert "seq=1 record_id=rec-1 event_id=evt-1 status=confirmed" in output
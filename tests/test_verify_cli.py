import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from tc_api.cli.verify import main
from tc_api.trucon.evidence import compute_binding_expected_value


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


def _immutable_entry(event_id, event_type, digest, index, predicate_entries=None):
    return {
        "index": index,
        "event_id": event_id,
        "event_type": event_type,
        "digest": digest,
        "predicate_entries": predicate_entries or [],
        "subject_names": ["trusted-log-chain_default"],
        "signer_identity": "alice@example.com",
        "signer_identity_match": True,
        "errors": [],
    }


def _write_evidence(tmp_path, payload):
    evidence_path = Path(tmp_path) / "evidence.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    return str(evidence_path)


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
    assert captured["replay"]["entries"][0]["event_id"] == "evt-1"
    assert captured["fallback"]["note"] == "transitional live TruCon fallback"
    assert "profiles" in captured


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
    assert "Per-record replay detail:" in output
    assert "Profiles:" in output
    assert "event_id=evt-1" in output


def test_verify_cli_evidence_mode_success(tmp_path, capsys):
    baseline_rtmr = "11" * 48
    head_digest = "sha384:" + ("22" * 48)
    derived_mr = __import__("hashlib").sha384(bytes.fromhex(baseline_rtmr) + bytes.fromhex("22" * 48)).hexdigest()
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 2,
        "head_log_id": "log-tail",
        "mr_value": derived_mr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "head_event_digest": head_digest,
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 2, "log-tail", derived_mr),
        },
    }
    evidence_path = _write_evidence(tmp_path, evidence_payload)
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "chain_id": "default",
                "entry_count": 2,
                "entries": [
                    _immutable_entry("evt-1", "launch", head_digest, 1),
                    _immutable_entry(
                        "evt-log0-default",
                        "chain.init",
                        None,
                        2,
                        predicate_entries=[
                            {"key": "baseline_rtmr", "value": baseline_rtmr},
                            {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                            {"key": "pub_key", "value": "pem"},
                        ],
                    ),
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["mode"]["input_mode"] == "evidence-backed"
    assert captured["summary"]["status"] == "verified"
    assert captured["attested_head"]["matches_replay"] is True
    assert captured["replay"]["derived"]["sequence_num"] == 2


def test_verify_cli_rejects_invalid_evidence_binding(tmp_path, capsys):
    evidence_path = _write_evidence(
        tmp_path,
        {
            "version": "v1",
            "tee_type": "tdx",
            "chain_id": "default",
            "sequence_num": 1,
            "head_log_id": "log-tail",
            "mr_value": "aa" * 48,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quote": "base64-quote",
            "report_data_binding": {
                "algorithm": "sha384",
                "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
                "expected_value": "sha384:" + ("ff" * 48),
            },
        },
    )

    exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "failed"
    assert "Invalid evidence package" in captured["errors"][0]


def test_verify_cli_rejects_expired_evidence(tmp_path, capsys):
    baseline_rtmr = "11" * 48
    head_digest = "sha384:" + ("22" * 48)
    derived_mr = __import__("hashlib").sha384(bytes.fromhex(baseline_rtmr) + bytes.fromhex("22" * 48)).hexdigest()
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 2,
        "head_log_id": "log-tail",
        "mr_value": derived_mr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 2, "log-tail", derived_mr),
        },
    }
    evidence_path = _write_evidence(tmp_path, evidence_payload)
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "chain_id": "default",
                "entry_count": 2,
                "entries": [
                    _immutable_entry("evt-1", "launch", head_digest, 1),
                    _immutable_entry(
                        "evt-log0-default",
                        "chain.init",
                        None,
                        2,
                        predicate_entries=[{"key": "baseline_rtmr", "value": baseline_rtmr}],
                    ),
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["attested_head"]["expired"] is True
    assert "Evidence package has expired" in captured["errors"]


def test_verify_cli_evidence_mode_detects_replay_mismatch(tmp_path, capsys):
    baseline_rtmr = "11" * 48
    replay_digest = "sha384:" + ("22" * 48)
    wrong_mr = "44" * 48
    evidence_path = _write_evidence(
        tmp_path,
        {
            "version": "v1",
            "tee_type": "tdx",
            "chain_id": "default",
            "sequence_num": 2,
            "head_log_id": "log-tail",
            "mr_value": wrong_mr,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "quote": "base64-quote",
            "report_data_binding": {
                "algorithm": "sha384",
                "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
                "expected_value": compute_binding_expected_value("default", 2, "log-tail", wrong_mr),
            },
        },
    )
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "chain_id": "default",
                "entry_count": 2,
                "entries": [
                    _immutable_entry("evt-1", "launch", replay_digest, 1),
                    _immutable_entry(
                        "evt-log0-default",
                        "chain.init",
                        None,
                        2,
                        predicate_entries=[{"key": "baseline_rtmr", "value": baseline_rtmr}],
                    ),
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["attested_head"]["matches_replay"] is False
    assert any("mr_value mismatch" in error for error in captured["errors"])
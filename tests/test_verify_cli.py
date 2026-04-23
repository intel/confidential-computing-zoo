import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

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


def _immutable_entry(event_id, event_type, digest, index, predicate_entries=None, chain_id="default"):
    return {
        "index": index,
        "sequence_num": index,
        "event_id": event_id,
        "event_type": event_type,
        "digest": digest,
        "predicate_entries": predicate_entries or [],
        "prev_event_digest": None,
        "prev_lookup_hash": None,
        "predecessor_ok": True,
        "predecessor_status": "origin" if index == 1 else "proven",
        "candidate_count": 0,
        "materialized_candidate_count": 0,
        "matched_candidate_count": 0,
        "boundary_status": None,
        "public_history_ok": True,
        "public_history_status": "public",
        "replay_provenance": "public",
        "subject_names": [f"trusted-log-chain_{chain_id}"],
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
                "predecessor_ok": None,
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
                        "predecessor_ok": True,
                        "predecessor_status": "origin",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": None,
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["summary"]["status"] == "verified"
    assert captured["mode"]["verification_mode"] == "tee"
    assert captured["replay"]["entries"][0]["event_id"] == "evt-1"
    assert captured["replay"]["entries"][0]["predecessor_status"] == "origin"
    assert captured["mode"]["input_mode"] == "live-troubleshooting"
    assert captured["fallback"]["note"] == "explicit internal troubleshooting mode"
    assert captured["diagnostics"]["replay"]["success"] is True
    assert captured["diagnostics"]["fallback"]["valid"] is True
    assert "profiles" in captured


def test_verify_cli_rejects_bare_chain_id_without_troubleshooting_flag():
    with pytest.raises(SystemExit) as exc_info:
        main(["default", "--json"])

    assert exc_info.value.code == 2


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
            exit_code = main(["default", "--troubleshoot-live", "--json", "--require-tee"])

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
                "predecessor_ok": True,
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
                "predecessor_ok": None,
                "error": None,
            },
        ],
    }

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        exit_code = main(["default", "--troubleshoot-live", "--json", "--fail-on-pending"])

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
                "predecessor_ok": None,
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
                "entry_count": 1,
                "entries": [
                    {
                        "event_id": "evt-1",
                        "predecessor_ok": True,
                        "predecessor_status": "origin",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": None,
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Per-record replay detail:" in output
    assert "Troubleshooting:" in output
    assert "Diagnostics:" in output
    assert "Profiles:" in output
    assert "event_id=evt-1" in output
    assert "predecessor_status=origin" in output


def test_verify_cli_json_preserves_boundary_status(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": False,
        "chain_id": "default",
        "total_entries": 1,
        "mr_verified": 0,
        "rekor_confirmed": 1,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": 1,
        "entries": [
            {
                "seq": 1,
                "record_id": "rec-1",
                "event_id": "evt-1",
                "mr_ok": None,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": None,
                "predecessor_ok": None,
                "predecessor_status": "unverifiable",
                "boundary_status": "degraded",
                "candidate_count": 0,
                "materialized_candidate_count": 0,
                "matched_candidate_count": 0,
                "error": "signed predecessor contract unavailable",
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
                        "predecessor_ok": None,
                        "predecessor_status": "unverifiable",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": "degraded",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["replay"]["entries"][0]["boundary_status"] == "degraded"
    assert captured["diagnostics"]["replay"]["first_entry_issue"]["boundary_status"] == "degraded"


def test_verify_cli_text_reports_degraded_rollout_guidance(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": True,
        "chain_id": "default",
        "total_entries": 2,
        "mr_verified": 0,
        "rekor_confirmed": 2,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": None,
        "entries": [],
    }
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": True,
            "errors": [],
            "details": {
                "entry_count": 2,
                "entries": [
                    {
                        "event_id": "evt-2",
                        "event_type": "launch",
                        "predecessor_ok": None,
                        "predecessor_status": "unverifiable",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": "degraded",
                    },
                    {
                        "event_id": "evt-1",
                        "event_type": "chain.init",
                        "predecessor_ok": True,
                        "predecessor_status": "origin",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": None,
                    },
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "rollout=degraded" in output
    assert "mixed-regime migration state" in output


def test_verify_cli_text_reports_invalid_rollout_guidance(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": False,
        "chain_id": "default",
        "total_entries": 3,
        "mr_verified": 0,
        "rekor_confirmed": 3,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": 3,
        "entries": [],
    }
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": False,
            "errors": ["Signed predecessor continuity verification failed"],
            "details": {
                "entry_count": 3,
                "entries": [
                    {
                        "event_id": "evt-3",
                        "event_type": "launch",
                        "predecessor_ok": False,
                        "predecessor_status": "unverifiable",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": "invalid",
                    },
                    {
                        "event_id": "evt-2",
                        "event_type": "launch",
                        "predecessor_ok": True,
                        "predecessor_status": "proven",
                        "candidate_count": 1,
                        "materialized_candidate_count": 1,
                        "matched_candidate_count": 1,
                        "boundary_status": None,
                    },
                    {
                        "event_id": "evt-1",
                        "event_type": "chain.init",
                        "predecessor_ok": True,
                        "predecessor_status": "origin",
                        "candidate_count": 0,
                        "materialized_candidate_count": 0,
                        "matched_candidate_count": 0,
                        "boundary_status": None,
                    },
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "rollout=invalid" in output
    assert "regressed to incompatible legacy linkage" in output
    assert "first_entry_issue=" in output


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
    assert captured["replay"]["provenance"]["status"] == "public"
    assert captured["attested_head"]["contract_scope"] == "current-head binding only"
    assert captured["replay"]["derived"]["sequence_num"] == 2


def test_verify_cli_json_preserves_replay_provenance_boundary(tmp_path, capsys):
    baseline_rtmr = "44" * 48
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": baseline_rtmr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 1, "log-tail", baseline_rtmr),
        },
    }
    evidence_path = _write_evidence(tmp_path, evidence_payload)
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": False,
            "errors": ["Signed predecessor continuity verification failed"],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "chain_id": "default",
                "entry_count": 1,
                "entries": [
                    {
                        **_immutable_entry(
                            "evt-log0-default",
                            "chain.init",
                            "sha384:" + ("22" * 48),
                            1,
                            predicate_entries=[
                                {"key": "baseline_rtmr", "value": baseline_rtmr},
                                {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                                {"key": "pub_key", "value": "pem"},
                            ],
                        ),
                        "predecessor_ok": False,
                        "predecessor_status": "unsupported",
                        "public_history_ok": False,
                        "public_history_status": "cache-assisted",
                        "replay_provenance": "cache-assisted",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["replay"]["provenance"]["status"] == "unsupported"
    assert captured["attested_head"]["valid"] is True
    assert captured["summary"]["status"] == "failed"


def test_verify_cli_json_reports_mirrored_verification_tier(tmp_path, capsys):
    baseline_rtmr = "44" * 48
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": baseline_rtmr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 1, "log-tail", baseline_rtmr),
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
                "entry_count": 1,
                "entries": [
                    {
                        **_immutable_entry(
                            "evt-log0-default",
                            "chain.init",
                            "sha384:" + ("22" * 48),
                            1,
                            predicate_entries=[
                                {"key": "baseline_rtmr", "value": baseline_rtmr},
                                {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                                {"key": "pub_key", "value": "pem"},
                            ],
                        ),
                        "history_materialization_provenance": "mirror",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["replay"]["provenance"]["status"] == "mirrored"
    assert captured["summary"]["verification_tier"] == "public+mirrored+attested"


def test_verify_cli_json_reports_attestation_storage_verification_tier(tmp_path, capsys):
    baseline_rtmr = "44" * 48
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": baseline_rtmr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 1, "log-tail", baseline_rtmr),
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
                "entry_count": 1,
                "entries": [
                    {
                        **_immutable_entry(
                            "evt-log0-default",
                            "chain.init",
                            "sha384:" + ("22" * 48),
                            1,
                            predicate_entries=[
                                {"key": "baseline_rtmr", "value": baseline_rtmr},
                                {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                                {"key": "pub_key", "value": "pem"},
                            ],
                        ),
                        "history_materialization_provenance": "attestation-storage",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["replay"]["provenance"]["status"] == "attestation-storage"
    assert captured["summary"]["verification_tier"] == "public+attestation-storage"


def test_verify_cli_text_reports_verification_tier(capsys):
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
        "entries": [],
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
                "entries": [{**_immutable_entry("evt-1", "launch", "sha384:evt-1", 1), "history_materialization_provenance": "mirror"}],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Verification tier: public+mirrored" in output


def test_verify_cli_text_explains_attestation_storage_provenance(capsys):
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
        "entries": [],
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
                        **_immutable_entry("evt-1", "launch", "sha384:evt-1", 1),
                        "history_materialization_provenance": "attestation-storage",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Verification tier: public+attestation-storage" in output
    assert "provenance=attestation-storage historical continuity required Rekor-hosted attestation materialization" in output


def test_verify_cli_text_explains_provenance_split(tmp_path, capsys):
    baseline_rtmr = "44" * 48
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": baseline_rtmr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 1, "log-tail", baseline_rtmr),
        },
    }
    evidence_path = _write_evidence(tmp_path, evidence_payload)
    immutable_result = type(
        "VerifyResult",
        (),
        {
            "success": False,
            "errors": ["Signed predecessor continuity verification failed"],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "chain_id": "default",
                "entry_count": 1,
                "entries": [
                    {
                        **_immutable_entry(
                            "evt-log0-default",
                            "chain.init",
                            "sha384:" + ("22" * 48),
                            1,
                            predicate_entries=[
                                {"key": "baseline_rtmr", "value": baseline_rtmr},
                                {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                                {"key": "pub_key", "value": "pem"},
                            ],
                        ),
                        "predecessor_ok": False,
                        "predecessor_status": "unsupported",
                        "public_history_ok": False,
                        "public_history_status": "cache-assisted",
                        "replay_provenance": "cache-assisted",
                    }
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "trust_sources=public_replay(history, baseline) + exported_evidence(current_head_binding)" in output
    assert "provenance=unsupported historical replay facts depended on process-local cache" in output


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


def test_verify_cli_evidence_mode_rejects_non_default_chain_without_baseline(tmp_path, capsys):
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "workload-a",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": "44" * 48,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": "base64-quote",
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("workload-a", 1, "log-tail", "44" * 48),
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
                "subject": "trusted-log-chain_workload-a",
                "chain_id": "workload-a",
                "entry_count": 1,
                "entries": [
                    _immutable_entry("evt-1", "launch", "sha384:" + ("22" * 48), 1, chain_id="workload-a"),
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "failed"
    assert any("did not begin with Event Log 0" in error for error in captured["errors"])


def test_verify_cli_live_fallback_fails_non_default_chain_without_baseline(capsys):
    chain_state = {"chain_id": "workload-a", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": False,
        "chain_id": "workload-a",
        "total_entries": 1,
        "mr_verified": 0,
        "rekor_confirmed": 1,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": 1,
        "entries": [
            {
                "seq": 1,
                "record_id": "rec-1",
                "event_id": "evt-1",
                "mr_ok": None,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": None,
                "predecessor_ok": True,
                "error": "non-default chain 'workload-a' does not begin with Event Log 0",
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
                "subject": "trusted-log-chain_workload-a",
                "chain_id": "workload-a",
                "entry_count": 1,
                "entries": [
                    _immutable_entry("evt-1", "launch", "sha384:" + ("22" * 48), 1, chain_id="workload-a"),
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["workload-a", "--troubleshoot-live", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "failed"
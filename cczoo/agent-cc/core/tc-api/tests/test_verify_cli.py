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
import os
import base64
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from tc_api.cli.verify import _normalize_replay_entries, main
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from tc_api.trucon.evidence import (
    BINDING_ALGORITHM,
    REQUIRED_BOUND_FIELDS,
    compute_binding_expected_value,
    decode_binding_expected_value,
)


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, exc, _tb):
        return False


def _urlopen_factory(chain_state_payload, verify_payload):
    def _urlopen(request, timeout=15):
        url = request.full_url
        if url.endswith("/chain-state"):
            return _Response(chain_state_payload)
        if url.endswith("/verify-chain"):
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
    payload = dict(payload)
    if "report_data_binding" in payload:
        binding = dict(payload["report_data_binding"])
        binding.setdefault("algorithm", BINDING_ALGORITHM)
        binding.setdefault("bound_fields", list(REQUIRED_BOUND_FIELDS))
        binding["algorithm"] = BINDING_ALGORITHM
        binding["bound_fields"] = list(REQUIRED_BOUND_FIELDS)
        payload["report_data_binding"] = binding
    if payload.get("quote") == "base64-quote":
        try:
            payload["quote"] = _build_tdx_quote_v4(
                payload["report_data_binding"]["expected_value"],
                payload.get("mr_value"),
            )
        except ValueError:
            pass
    evidence_path = Path(tmp_path) / "evidence.json"
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    return str(evidence_path)


def _build_tdx_quote_v4(expected_value: str, rtmr2_hex: str | None) -> str:
    header = bytearray(48)
    struct.pack_into("<H", header, 0, 4)

    body = bytearray(584)
    expected_bytes = decode_binding_expected_value(expected_value)
    body[0x208:0x208 + len(expected_bytes)] = expected_bytes
    if rtmr2_hex:
        body[0x148 + (2 * 48):0x148 + (3 * 48)] = bytes.fromhex(rtmr2_hex)

    return base64.b64encode(bytes(header + body)).decode("ascii")


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
                "head_log_verification": {
                    "status": "verified",
                    "scope": "accepted-head-only",
                    "log_id": "log-tail",
                    "entry_uuid": "uuid-log-tail",
                    "log_index": 123,
                    "inclusion_status": "verified",
                    "checkpoint_status": "verified",
                    "checkpoint_origin": "rekor.sigstore.dev - 2605736670972794746",
                    "bootstrap_trust": {
                        "configured": True,
                        "source": "TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_FILE",
                        "consistency_proven": False,
                    },
                    "proof": {"root_hash": "abcd", "tree_size": 1, "hashes": []},
                    "reasons": [],
                },
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
    assert captured["log_verification"]["status"] == "verified"
    assert captured["log_verification"]["bootstrap_trust"]["source"] == "TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_FILE"
    assert "historical consistency across time is not proven" in captured["log_verification"]["limitations"][0]
    assert "profiles" in captured


def test_verify_cli_live_troubleshooting_reports_head_log_degraded(capsys):
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
                "head_log_verification": {
                    "status": "degraded",
                    "scope": "accepted-head-only",
                    "log_id": "log-tail",
                    "inclusion_status": "verified",
                    "checkpoint_status": "unconfigured",
                    "bootstrap_trust": {
                        "configured": False,
                        "source": None,
                        "consistency_proven": False,
                    },
                    "reasons": ["accepted head checkpoint trust source was not configured"],
                },
                "entries": [{**_immutable_entry("evt-1", "launch", "sha384:evt-1", 1)}],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "troubleshooting-only"
    assert captured["log_verification"]["status"] == "troubleshooting-only"
    assert captured["log_verification"]["checkpoint_status"] == "unconfigured"


def test_verify_cli_live_troubleshooting_fails_on_invalid_head_log_verification(capsys):
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
            "success": False,
            "errors": ["Accepted head-entry transparency-log verification failed"],
            "details": {
                "source": "immutable_backend",
                "subject": "trusted-log-chain_default",
                "entry_count": 1,
                "head_log_verification": {
                    "status": "failed",
                    "scope": "accepted-head-only",
                    "log_id": "log-tail",
                    "inclusion_status": "verified",
                    "checkpoint_status": "invalid",
                    "bootstrap_trust": {
                        "configured": True,
                        "source": "explicit-policy",
                        "consistency_proven": False,
                    },
                    "reasons": ["accepted head checkpoint validation failed: invalid signature"],
                },
                "entries": [{**_immutable_entry("evt-1", "launch", "sha384:evt-1", 1)}],
            },
        },
    )()

    with patch("tc_api.cli.verify.urllib.request.urlopen", side_effect=_urlopen_factory(chain_state, trucon_verify)):
        with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
            MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
            exit_code = main(["default", "--troubleshoot-live", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["summary"]["status"] == "failed"
    assert captured["log_verification"]["status"] == "failed"
    assert captured["log_verification"]["checkpoint_status"] == "invalid"


def test_sigstore_payload_hash_lookup_retries_after_timeout():
    attempts = []

    def _urlopen(request, timeout=15):
        attempts.append(timeout)
        if len(attempts) < 3:
            raise TimeoutError("The read operation timed out")
        return _Response(["12345"])

    with patch.dict(os.environ, {
        "TC_API_REKOR_PAYLOAD_LOOKUP_RETRIES": "3",
        "TC_API_REKOR_PAYLOAD_LOOKUP_BACKOFF_SECONDS": "0",
        "TC_API_REKOR_PAYLOAD_LOOKUP_TIMEOUT_SECONDS": "7",
    }, clear=False):
        adapter = SigstoreLogAdapter()

    with patch("tlog.backends.rekor.adapter.urllib.request.urlopen", side_effect=_urlopen):
        with patch.object(adapter, "get_entry", return_value={"uuid": "12345", "body": {"spec": {"payload": "e30="}}}) as mock_get_entry:
            results = adapter.find_entries_by_payload_hash("sha256:test")

    assert attempts == [7.0, 7.0, 7.0]
    assert len(results) == 1
    assert results[0]["uuid"] == "12345"
    mock_get_entry.assert_called_once_with("12345")


def test_sigstore_payload_hash_lookup_retries_when_candidates_are_unmaterialized():
    with patch.dict(os.environ, {
        "TC_API_REKOR_PAYLOAD_LOOKUP_RETRIES": "2",
        "TC_API_REKOR_PAYLOAD_LOOKUP_BACKOFF_SECONDS": "0",
        "TC_API_REKOR_PAYLOAD_LOOKUP_TIMEOUT_SECONDS": "7",
    }, clear=False):
        adapter = SigstoreLogAdapter()

    with patch("tlog.backends.rekor.adapter.urllib.request.urlopen", return_value=_Response(["12345"])):
        with patch.object(
            adapter,
            "get_entry",
            side_effect=[
                {"uuid": "12345", "body": {"spec": {"payloadHash": {"algorithm": "sha256", "value": "deadbeef"}}}},
                {"uuid": "12345", "body": {"spec": {"payload": "e30="}}},
            ],
        ) as mock_get_entry:
            results = adapter.find_entries_by_payload_hash("sha256:test")

    assert len(results) == 1
    assert results[0]["uuid"] == "12345"
    assert mock_get_entry.call_count == 2


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


def test_normalize_replay_entries_preserves_predicate_entries():
    entries = [
        {
            "index": 1,
            "event_id": "evt-1",
            "event_type": "launch",
            "sequence_num": 2,
            "digest": "sha384:abc",
            "created": "2026-01-01T00:00:00Z",
            "prev_event_digest": "sha384:def",
            "prev_lookup_hash": "sha256:123",
            "predecessor_ok": True,
            "candidate_count": 1,
            "materialized_candidate_count": 1,
            "matched_candidate_count": 1,
            "predecessor_status": "proven",
            "owner_status": None,
            "boundary_status": None,
            "public_history_ok": True,
            "public_history_status": "public",
            "replay_provenance": "attestation-storage",
            "history_materialization_provenance": "attestation-storage",
            "predicate_entries": [{"key": "launch_id", "value": "launch-123"}],
            "subject_names": ["trusted-log-chain_default"],
            "signer_identity": "alice@example.com",
            "signer_identity_match": True,
            "errors": [],
        }
    ]

    normalized = _normalize_replay_entries(entries)

    assert normalized[0]["predicate_entries"] == [{"key": "launch_id", "value": "launch-123"}]


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


def test_verify_cli_json_reports_owner_failure_diagnostics(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": False,
        "chain_id": "default",
        "total_entries": 2,
        "mr_verified": 0,
        "rekor_confirmed": 2,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": 2,
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
                "predecessor_status": "origin",
                "owner_ok": True,
                "owner_status": "origin",
                "error": None,
            },
            {
                "seq": 2,
                "record_id": "rec-2",
                "event_id": "evt-2",
                "mr_ok": None,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": None,
                "predecessor_ok": True,
                "predecessor_status": "proven",
                "owner_ok": False,
                "owner_status": "invalid",
                "error": "owner authorization signature mismatch",
            },
        ],
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
                    _immutable_entry("evt-2", "launch", "sha384:evt-2", 2),
                    _immutable_entry("evt-1", "chain.init", "sha384:evt-1", 1),
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
    assert captured["diagnostics"]["fallback"]["owner_status_counts"]["invalid"] == 1
    assert captured["diagnostics"]["fallback"]["first_entry_issue"]["owner_status"] == "invalid"


def test_verify_cli_text_reports_owner_failure_detail(capsys):
    chain_state = {"chain_id": "default", "head_log_id": "log-tail"}
    trucon_verify = {
        "valid": False,
        "chain_id": "default",
        "total_entries": 2,
        "mr_verified": 0,
        "rekor_confirmed": 2,
        "rekor_pending": 0,
        "rtmr_available": False,
        "head_mr_value": None,
        "first_error_at": 2,
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
                "predecessor_status": "origin",
                "owner_ok": True,
                "owner_status": "origin",
                "error": None,
            },
            {
                "seq": 2,
                "record_id": "rec-2",
                "event_id": "evt-2",
                "mr_ok": None,
                "rekor_ok": True,
                "rtmr_extended": True,
                "mr_value": None,
                "predecessor_ok": True,
                "predecessor_status": "proven",
                "owner_ok": False,
                "owner_status": "invalid",
                "error": "owner authorization signature mismatch",
            },
        ],
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
                    _immutable_entry("evt-2", "launch", "sha384:evt-2", 2),
                    _immutable_entry("evt-1", "chain.init", "sha384:evt-1", 1),
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
    assert "fallback_first_entry_issue=" in output
    assert "owner_status=invalid" in output
    assert "Fallback per-record detail:" in output


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
    assert captured["attested_head"]["quote_parse"]["parsed"] is True
    assert captured["attested_head"]["quote_parse"]["report_data_prefix_matches_binding"] is True
    assert captured["attested_head"]["quote_parse"]["mr_value_matches_quote"] is True
    assert captured["replay"]["provenance"]["status"] == "public"
    assert captured["attested_head"]["contract_scope"] == "current-head binding only"
    assert captured["replay"]["derived"]["sequence_num"] == 2


def test_verify_cli_quote_mode_success(tmp_path, capsys):
    baseline_rtmr = "11" * 48
    head_digest = "sha384:" + ("22" * 48)
    derived_mr = __import__("hashlib").sha384(bytes.fromhex(baseline_rtmr) + bytes.fromhex("22" * 48)).hexdigest()
    expected_value = compute_binding_expected_value("default", 2, "log-tail", derived_mr)
    quote_value = _build_tdx_quote_v4(expected_value, derived_mr)
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
        exit_code = main(["default", "--quote", quote_value, "--head-log-id", "log-tail", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["mode"]["input_mode"] == "quote-backed"
    assert captured["summary"]["status"] == "verified"
    assert captured["target"]["source"] == "direct-quote"
    assert captured["attested_head"]["source"] == "argument"
    assert captured["attested_head"]["quote_parse"]["parsed"] is True
    assert captured["attested_head"]["quote_parse"]["report_data_prefix_matches_binding"] is True
    assert captured["attested_head"]["quote_parse"]["mr_value_matches_quote"] is True
    assert captured["attested_head"]["expected_value"] == expected_value


def test_verify_cli_quote_mode_detects_binding_mismatch(capsys):
    baseline_rtmr = "11" * 48
    head_digest = "sha384:" + ("22" * 48)
    derived_mr = __import__("hashlib").sha384(bytes.fromhex(baseline_rtmr) + bytes.fromhex("22" * 48)).hexdigest()
    wrong_expected_value = compute_binding_expected_value("default", 1, "wrong-log", derived_mr)
    quote_value = _build_tdx_quote_v4(wrong_expected_value, derived_mr)
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
                    _immutable_entry(
                        "evt-log0-default",
                        "chain.init",
                        head_digest,
                        1,
                        predicate_entries=[
                            {"key": "baseline_rtmr", "value": derived_mr},
                            {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                            {"key": "pub_key", "value": "pem"},
                        ],
                    )
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["default", "--quote", quote_value, "--head-log-id", "log-tail", "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["mode"]["input_mode"] == "quote-backed"
    assert captured["attested_head"]["quote_parse"]["report_data_prefix_matches_binding"] is False
    assert any("Quote REPORTDATA prefix did not match the expected head_log_id binding bytes" in error for error in captured["errors"])


def test_verify_cli_quote_mode_requires_head_log_id():
    with pytest.raises(SystemExit) as exc_info:
        main(["default", "--quote", "Zm9v"])

    assert exc_info.value.code == 2


def test_verify_cli_evidence_mode_detects_quote_rtmr_mismatch(tmp_path, capsys):
    baseline_rtmr = "11" * 48
    evidence_mr = baseline_rtmr
    evidence_payload = {
        "version": "v1",
        "tee_type": "tdx",
        "chain_id": "default",
        "sequence_num": 1,
        "head_log_id": "log-tail",
        "mr_value": evidence_mr,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "quote": _build_tdx_quote_v4(
            compute_binding_expected_value("default", 1, "log-tail", evidence_mr),
            "22" * 48,
        ),
        "report_data_binding": {
            "algorithm": "sha384",
            "bound_fields": ["chain_id", "sequence_num", "head_log_id", "mr_value"],
            "expected_value": compute_binding_expected_value("default", 1, "log-tail", evidence_mr),
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
                    _immutable_entry(
                        "evt-log0-default",
                        "chain.init",
                        "sha384:" + ("22" * 48),
                        1,
                        predicate_entries=[
                            {"key": "baseline_rtmr", "value": evidence_mr},
                            {"key": "ccel_digest", "value": "sha384:" + ("33" * 48)},
                            {"key": "pub_key", "value": "pem"},
                        ],
                    )
                ],
            },
        },
    )()

    with patch("tc_api.cli.verify.TrustedLogAPI") as MockTrustedLogAPI:
        MockTrustedLogAPI.return_value.verify_record.return_value = immutable_result
        exit_code = main(["--evidence", evidence_path, "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert captured["attested_head"]["quote_parse"]["parsed"] is True
    assert captured["attested_head"]["quote_parse"]["mr_value_matches_quote"] is False
    assert any("Quote RTMR[2] did not match evidence mr_value" in error for error in captured["errors"])


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
                "head_log_verification": {
                    "status": "verified",
                    "scope": "accepted-head-only",
                    "log_id": "log-tail",
                    "entry_uuid": "uuid-log-tail",
                    "log_index": 123,
                    "inclusion_status": "verified",
                    "checkpoint_status": "verified",
                    "bootstrap_trust": {
                        "configured": True,
                        "source": "TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_FILE",
                        "consistency_proven": False,
                    },
                    "reasons": [],
                },
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
    assert "Head log verification:" in output
    assert "bootstrap_trust_configured=True source=TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_FILE historical_consistency_proven=False" in output
    assert "historical consistency across time is not proven" in output


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
                "expected_value": "head_log_id_bytes:zz",
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
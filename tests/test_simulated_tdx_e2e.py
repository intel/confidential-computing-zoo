import base64
import importlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tc_api.cli.verify import main as verify_main
from tc_api.tlog.local_mr import LocalMRAdapter
from tc_api.tlog_client import compute_entry_digest, compute_event_digest
from tc_api.trucon.database import init_db

trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")


class SimulatedMRAdapter(LocalMRAdapter):
    def __init__(self) -> None:
        self._current = "11" * 48

    def read(self, index: int) -> str:
        return self._current

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        previous = self._current
        self._current = __import__("hashlib").sha384(
            bytes.fromhex(previous) + bytes.fromhex(digest.removeprefix("sha384:"))
        ).hexdigest()
        return self._current, previous


@dataclass
class MockQuoteMaterial:
    quote: str
    report_data: str
    quote_format: str = "tdx-configfs-tsm"


class EchoQuoteAdapter:
    def quote(self, expected_value: str) -> MockQuoteMaterial:
        return MockQuoteMaterial(quote="base64-simulated-quote", report_data=expected_value)


class DummyBundle:
    def __init__(self, source_json: str) -> None:
        self.source_json = source_json


class FakeImmutableBackend:
    def __init__(self) -> None:
        self._entries_by_chain: dict[str, list[dict[str, Any]]] = {}
        self._entries_by_log_id: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def submit_bundle(self, bundle: DummyBundle, prev_log_id: Optional[str] = None):
        statement = json.loads(bundle.source_json)
        subject = (statement.get("subject") or [{}])[0]
        subject_name = subject.get("name", "trusted-log-chain_default")
        chain_id = subject_name.removeprefix("trusted-log-chain_")

        self._counter += 1
        log_id = f"fake-log-{self._counter}"
        payload_b64 = base64.b64encode(bundle.source_json.encode("utf-8")).decode("utf-8")
        entry = {
            "log_id": log_id,
            "body": {
                "spec": {
                    "payload": payload_b64,
                }
            },
        }
        self._entries_by_chain.setdefault(chain_id, []).append(entry)
        self._entries_by_log_id[log_id] = entry
        return log_id, "confirmed", {"log_id": log_id}

    def get_entry(self, log_id: str) -> Any:
        return self._entries_by_log_id.get(log_id)

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        tail_entry = self._entries_by_log_id[end_log_id]
        body = tail_entry["body"]
        payload_b64 = body["spec"]["payload"]
        statement = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
        subject_name = (statement.get("subject") or [{}])[0].get("name", "trusted-log-chain_default")
        chain_id = subject_name.removeprefix("trusted-log-chain_")
        chain_entries = self._entries_by_chain.get(chain_id, [])
        tail_index = next(i for i, entry in enumerate(chain_entries) if entry["log_id"] == end_log_id)
        window = chain_entries[: tail_index + 1]
        return list(reversed(window))[:count]


def _make_db_patches(db_path: str):
    names = [
        "insert_record",
        "get_chain_state",
        "update_chain_state",
        "get_record_by_idempotency_key",
        "get_latest_confirmed_record",
        "get_all_chain_ids",
        "get_failed_by_chain",
        "get_pending_by_chain",
        "set_status_submitting",
        "update_record_confirmed",
        "update_status",
        "get_queue_stats",
    ]
    originals = {name: getattr(trucon_db_mod, name) for name in names}

    def _wrap(name: str):
        original = originals[name]

        def wrapped(*args, **kwargs):
            kwargs.setdefault("db_path", db_path)
            return original(*args, **kwargs)

        return wrapped

    return {name: _wrap(name) for name in names}


def _statement_json(
    chain_id: str,
    event_id: str,
    event_type: str,
    digest: Optional[str],
    entries: list[dict[str, Any]],
    created: Optional[str] = None,
) -> str:
    statement = {
        "subject": [
            {
                "name": f"trusted-log-chain_{chain_id}",
                "digest": {"sha384": (digest or ("00" * 48)).removeprefix("sha384:")},
            }
        ],
        "predicate": {
            "event_id": event_id,
            "event_type": event_type,
            "created": created or datetime.now(timezone.utc).isoformat(),
            "entries": entries,
            "digest": digest,
        },
    }
    return json.dumps(statement)


@pytest.fixture
def simulated_tdx_harness(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    backend = FakeImmutableBackend()
    db_patches = _make_db_patches(db_path)

    old_auth = trucon_app_mod._AUTH_DISABLED
    old_local_mr = trucon_app_mod._local_mr
    old_quote_adapter = trucon_app_mod._quote_adapter
    old_immutable_log = trucon_app_mod._immutable_log
    old_tokens = trucon_app_mod._pending_init_tokens.copy()

    try:
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._pending_init_tokens.clear()

        with patch.object(trucon_app_mod, "acquire_instance_lock"), \
             patch.object(trucon_app_mod, "release_instance_lock"), \
             patch.object(trucon_app_mod, "_crash_recovery"), \
             patch.object(trucon_app_mod, "_submit_daemon_loop"), \
             patch.object(trucon_app_mod, "init_db"), \
             patch.object(trucon_app_mod, "compute_ccel_digest", return_value="sha384:" + ("33" * 48)), \
             patch.object(trucon_app_mod, "insert_record", side_effect=db_patches["insert_record"]), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=db_patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "update_chain_state", side_effect=db_patches["update_chain_state"]), \
             patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=db_patches["get_record_by_idempotency_key"]), \
             patch.object(trucon_app_mod, "get_latest_confirmed_record", side_effect=db_patches["get_latest_confirmed_record"]), \
             patch.object(trucon_app_mod, "get_all_chain_ids", side_effect=db_patches["get_all_chain_ids"]), \
             patch.object(trucon_app_mod, "get_failed_by_chain", side_effect=db_patches["get_failed_by_chain"]), \
             patch.object(trucon_app_mod, "get_pending_by_chain", side_effect=db_patches["get_pending_by_chain"]), \
             patch.object(trucon_app_mod, "set_status_submitting", side_effect=db_patches["set_status_submitting"]), \
             patch.object(trucon_app_mod, "update_record_confirmed", side_effect=db_patches["update_record_confirmed"]), \
             patch.object(trucon_app_mod, "update_status", side_effect=db_patches["update_status"]), \
             patch.object(trucon_app_mod, "get_queue_stats", side_effect=db_patches["get_queue_stats"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            trucon_app_mod._local_mr = SimulatedMRAdapter()
            trucon_app_mod._quote_adapter = EchoQuoteAdapter()
            trucon_app_mod._immutable_log = backend
            yield client, backend, tmp_path
    finally:
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._local_mr = old_local_mr
        trucon_app_mod._quote_adapter = old_quote_adapter
        trucon_app_mod._immutable_log = old_immutable_log
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod._pending_init_tokens.update(old_tokens)


def test_simulated_tdx_e2e_covers_evidence_export_and_verify(simulated_tdx_harness, capsys):
    client, backend, tmp_path = simulated_tdx_harness

    baseline = client.get("/init-chain/default/baseline")
    assert baseline.status_code == 200
    baseline_data = baseline.json()
    baseline_rtmr = baseline_data["rtmr_value"]
    ccel_digest = baseline_data["ccel_digest"]

    baseline_bundle = _statement_json(
        chain_id="default",
        event_id="evt-log0-default",
        event_type="chain.init",
        digest=None,
        entries=[
            {"key": "baseline_rtmr", "value": baseline_rtmr},
            {"key": "ccel_digest", "value": ccel_digest},
            {"key": "pub_key", "value": "-----BEGIN PUBLIC KEY-----\nsimulated\n-----END PUBLIC KEY-----"},
        ],
    )
    init_resp = client.post(
        "/init-chain",
        json={
            "chain_id": "default",
            "init_token": baseline_data["init_token"],
            "signed_bundle": baseline_bundle,
            "pub_key": "-----BEGIN PUBLIC KEY-----\nsimulated\n-----END PUBLIC KEY-----",
        },
    )
    assert init_resp.status_code == 200
    assert init_resp.json()["sequence_num"] == 1

    created = datetime.now(timezone.utc).isoformat()
    business_entries = [{"key": "operation_result", "value": "success"}]
    entry_digests = [compute_entry_digest(entry["key"], entry["value"]) for entry in business_entries]
    business_digest = compute_event_digest("evt-1", "launch", created, entry_digests)
    business_bundle = _statement_json(
        chain_id="default",
        event_id="evt-1",
        event_type="launch",
        digest=business_digest,
        entries=business_entries,
        created=created,
    )
    commit_resp = client.post(
        "/commit",
        json={
            "bundle": business_bundle,
            "chain_id": "default",
            "event_digest": business_digest,
            "event_id": "evt-1",
            "idempotency_key": "idem-simulated-e2e",
        },
    )
    assert commit_resp.status_code == 200
    commit_data = commit_resp.json()
    assert commit_data["sequence_num"] == 2

    with patch("sigstore.models.Bundle.from_json", side_effect=lambda raw: DummyBundle(raw)):
        trucon_app_mod._submit_daemon_tick()

    evidence_resp = client.get("/evidence/default")
    assert evidence_resp.status_code == 200
    evidence = evidence_resp.json()
    assert evidence["tee_type"] == "tdx"
    assert evidence["sequence_num"] == 2
    assert evidence["head_log_id"] == "fake-log-2"
    assert evidence["quote"] == "base64-simulated-quote"

    evidence_path = Path(tmp_path) / "simulated-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")

    with patch("tc_api.cli.verify.SigstoreLogAdapter", return_value=backend):
        exit_code = verify_main(["--evidence", str(evidence_path), "--json"])

    captured = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert captured["summary"]["status"] == "verified"
    assert captured["attested_head"]["valid"] is True
    assert captured["attested_head"]["matches_replay"] is True
    assert captured["replay"]["derived"]["baseline_rtmr"] == baseline_rtmr
    assert captured["replay"]["derived"]["mr_value"] == evidence["mr_value"]
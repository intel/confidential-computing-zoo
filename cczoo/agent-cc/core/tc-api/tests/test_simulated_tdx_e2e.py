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
import importlib
import json
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.cli.verify import main as verify_main
from tlog.local_mr import LocalMRAdapter
from tlog.digest import compute_entry_digest, compute_event_digest
from tc_api.trucon.evidence import decode_binding_expected_value
from tc_api.trucon.database import init_db
from tc_api.trucon.owner_authorization import sign_owner_authorization
from tests.utils import make_db_patches

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
        return MockQuoteMaterial(
            quote=_build_tdx_quote_v4(expected_value, trucon_app_mod._local_mr.read(2)),
            report_data=expected_value,
        )


def _build_tdx_quote_v4(expected_value: str, rtmr2_hex: str | None) -> str:
    header = bytearray(48)
    struct.pack_into("<H", header, 0, 4)

    body = bytearray(584)
    if expected_value.startswith("sha384:"):
        expected_bytes = bytes.fromhex(expected_value.removeprefix("sha384:"))
    else:
        expected_bytes = decode_binding_expected_value(expected_value)
    body[0x208:0x208 + len(expected_bytes)] = expected_bytes
    if rtmr2_hex:
        body[0x148 + (2 * 48):0x148 + (3 * 48)] = bytes.fromhex(rtmr2_hex)

    return base64.b64encode(bytes(header + body)).decode("ascii")


class DummyBundle:
    def __init__(self, source_json: str) -> None:
        self.source_json = source_json
        payload_b64 = base64.b64encode(source_json.encode("utf-8")).decode("utf-8")

        class _Envelope:
            def __init__(self, payload: str) -> None:
                self._payload = payload

            def to_json(self) -> str:
                return json.dumps({"payload": self._payload})

        self._dsse_envelope = _Envelope(payload_b64)


class FakeImmutableBackend:
    def __init__(self) -> None:
        self._entries_by_chain: dict[str, list[dict[str, Any]]] = {}
        self._entries_by_log_id: dict[str, dict[str, Any]] = {}
        self._counter = 0

    def submit_bundle(self, bundle, prev_log_id: Optional[str] = None):
        source_json = bundle if isinstance(bundle, str) else bundle.source_json
        statement = json.loads(source_json)
        subject = (statement.get("subject") or [{}])[0]
        subject_name = subject.get("name", "trusted-log-chain_default")
        chain_id = subject_name.removeprefix("trusted-log-chain_")

        self._counter += 1
        log_id = f"fake-log-{self._counter}"
        payload_b64 = base64.b64encode(source_json.encode("utf-8")).decode("utf-8")
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


def _statement_json(
    chain_id: str,
    event_id: str,
    event_type: str,
    digest: Optional[str],
    entries: list[dict[str, Any]],
    created: Optional[str] = None,
    sequence_num: Optional[int] = None,
    prev_event_digest: Optional[str] = None,
    prev_lookup_hash: Optional[str] = None,
) -> str:
    created_value = created or datetime.now(timezone.utc).isoformat()
    entry_digests = [compute_entry_digest(entry["key"], entry["value"]) for entry in entries]
    predicate_digest = digest or compute_event_digest(event_id, event_type, created_value, entry_digests)
    statement = {
        "subject": [
            {
                "name": f"trusted-log-chain_{chain_id}",
                "digest": {"sha384": predicate_digest.removeprefix("sha384:")},
            }
        ],
        "predicate": {
            "event_id": event_id,
            "event_type": event_type,
            "created": created_value,
            "entries": entries,
            "digest": predicate_digest,
            "chain_id": chain_id,
            "sequence_num": sequence_num,
            "prev_event_digest": prev_event_digest,
            "prev_lookup_hash": prev_lookup_hash,
        },
    }
    return json.dumps(statement)


@pytest.fixture
def simulated_tdx_harness(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    backend = FakeImmutableBackend()
    db_patches = make_db_patches(
        trucon_db_mod,
        db_path,
        [
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
        ],
    )

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
    owner_private_key = ec.generate_private_key(ec.SECP384R1())
    owner_pub_key = owner_private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

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
            {"key": "pub_key", "value": owner_pub_key},
        ],
        sequence_num=1,
        prev_event_digest=None,
        prev_lookup_hash=None,
    )
    reserve = client.post(
        "/commit-intents/reserve",
        json={"chain_id": "default", "idempotency_key": "init-default", "is_baseline": True},
    )
    assert reserve.status_code == 200
    baseline_predicate = json.loads(baseline_bundle)["predicate"]
    baseline_digest = baseline_predicate["digest"]
    baseline_lookup_hash = "sha256:" + __import__("hashlib").sha256(baseline_bundle.encode("utf-8")).hexdigest()
    with patch("tc_api.trucon.bundles.Bundle.from_json", side_effect=lambda raw: DummyBundle(raw)):
        init_resp = client.post(
            "/init-chain",
            json={
                "chain_id": "default",
                "init_token": baseline_data["init_token"],
                "intent_token": reserve.json()["intent_token"],
                "signed_bundle": baseline_bundle,
                "pub_key": owner_pub_key,
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
            sequence_num=2,
            prev_event_digest=baseline_digest,
            prev_lookup_hash=baseline_lookup_hash,
        )
        business_payload = json.loads(business_bundle)
        business_payload["predicate"]["owner_authorization"] = sign_owner_authorization(
            owner_private_key,
            "default",
            2,
            baseline_digest,
            baseline_lookup_hash,
            business_digest,
        )
        business_bundle = json.dumps(business_payload)
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

        trucon_app_mod._submit_daemon_tick()

    evidence_resp = client.get("/evidence")
    assert evidence_resp.status_code == 200
    evidence = evidence_resp.json()
    assert evidence["tee_type"] == "tdx"
    assert evidence["sequence_num"] == 2
    assert evidence["head_log_id"] == "fake-log-2"
    assert isinstance(evidence["quote"], str)
    assert evidence["quote"]

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
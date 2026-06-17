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

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import importlib
import pytest
from fastapi.testclient import TestClient

from tc_api.trucon.database import init_db, insert_record, update_chain_state, update_record_confirmed
from tc_api.trucon.openviking_context_gate import (
    ContextSendPolicy,
    InMemoryTrustCache,
    verify_context_send_payload,
)
from tests.utils import StaticQuoteAdapter, make_db_patches

trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")


@pytest.fixture
def trucon_client(tmp_path):
    db_path = str(tmp_path / "test_openviking_gate.db")
    init_db(db_path)
    patches = make_db_patches(
        trucon_db_mod,
        db_path,
        ["get_chain_state", "get_latest_confirmed_record"],
    )

    old_auth = trucon_app_mod._AUTH_DISABLED
    old_quote_adapter = trucon_app_mod._quote_adapter

    try:
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._quote_adapter = None

        with patch.object(trucon_app_mod, "acquire_instance_lock"), \
             patch.object(trucon_app_mod, "release_instance_lock"), \
             patch.object(trucon_app_mod, "_crash_recovery"), \
             patch.object(trucon_app_mod, "_submit_daemon_loop"), \
             patch.object(trucon_app_mod, "init_db"), \
             patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
             patch.object(trucon_app_mod, "TdxQuoteAdapter", return_value=trucon_app_mod._quote_adapter), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "get_latest_confirmed_record", side_effect=patches["get_latest_confirmed_record"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client, db_path
    finally:
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._quote_adapter = old_quote_adapter


def _insert_confirmed_record(db_path: str, chain_id: str, sequence_num: int, log_id: str, mr_value: str):
    record_id = f"rec-{sequence_num}"
    insert_record(
        record_id=record_id,
        event_id=f"evt-{sequence_num}",
        payload={"bundle": "test", "chain_id": chain_id},
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        prev_log_id=None,
        mr_value=mr_value,
        sequence_num=sequence_num,
        event_digest="sha384:" + f"{sequence_num:02x}" * 48,
        db_path=db_path,
    )
    update_record_confirmed(record_id, log_id, db_path=db_path)
    update_chain_state(
        chain_id=chain_id,
        head_record_id=record_id,
        sequence_num=sequence_num,
        mr_value=mr_value,
        head_log_id=log_id,
        db_path=db_path,
    )


def test_confidential_evidence_endpoint_returns_required_claims(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    expected_value = trucon_app_mod.compute_binding_expected_value("default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value)

    response = client.get("/confidential/evidence")

    assert response.status_code == 200
    data = response.json()
    assert data["service_instance_id"]
    assert data["tee_type"] == "tdx"
    assert data["measurement_ref"] == "aa" * 48
    assert data["ledger_head_id"] == "log-1"
    assert data["policy_id"] == "openviking-context-send"
    assert data["policy_version"] == "2026-05-25"
    assert data["generated_at"]
    assert data["expires_at"]
    assert "attested_head_evidence" in data


def test_confidential_posture_endpoint_is_separate_from_evidence(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)

    response = client.get("/confidential/posture")

    assert response.status_code == 200
    data = response.json()
    assert data["kind"] == "openviking-confidential-posture"
    assert data["has_confirmed_ledger_head"] is True
    assert data["latest_ledger_head_id"] == "log-1"
    assert "attested_head_evidence" not in data


def test_verify_context_send_allows_and_reuses_cache(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    expected_value = trucon_app_mod.compute_binding_expected_value("default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value)
    payload = client.get("/confidential/evidence").json()
    cache = InMemoryTrustCache()
    policy = ContextSendPolicy(
        target_url="http://openviking.test",
        expected_service_instance_id=payload["service_instance_id"],
        expected_measurement_ref=payload["measurement_ref"],
        expected_policy_version=payload["policy_version"],
    )
    now = datetime.now(timezone.utc)

    first = verify_context_send_payload(payload, policy, cache=cache, now=now)
    second = verify_context_send_payload(payload, policy, cache=cache, now=now + timedelta(seconds=60))

    assert first.result == "allow"
    assert first.cache_hit is False
    assert second.result == "allow"
    assert second.cache_hit is True
    assert "prompt" not in first.decision_record
    assert "context" not in first.decision_record


def test_verify_context_send_denies_expired_evidence(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    expected_value = trucon_app_mod.compute_binding_expected_value("default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value)
    payload = client.get("/confidential/evidence").json()
    policy = ContextSendPolicy(
        target_url="http://openviking.test",
        expected_service_instance_id=payload["service_instance_id"],
        expected_measurement_ref=payload["measurement_ref"],
        expected_policy_version=payload["policy_version"],
    )
    future = datetime.fromisoformat(payload["expires_at"]) + timedelta(seconds=1)

    decision = verify_context_send_payload(payload, policy, now=future)

    assert decision.result == "deny"
    assert decision.reason == "evidence_expired"
    assert decision.fail_closed is True


def test_verify_context_send_denies_missing_required_claims():
    policy = ContextSendPolicy(target_url="http://openviking.test")

    decision = verify_context_send_payload({"kind": "openviking-confidential-evidence"}, policy)

    assert decision.result == "deny"
    assert decision.reason == "missing_required_claims"


def test_verify_context_send_denies_cache_key_mismatch(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    expected_value = trucon_app_mod.compute_binding_expected_value("default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value)
    payload = client.get("/confidential/evidence").json()
    cache = InMemoryTrustCache()
    policy = ContextSendPolicy(
        target_url="http://openviking.test",
        expected_service_instance_id=payload["service_instance_id"],
        expected_measurement_ref=payload["measurement_ref"],
        expected_policy_version=payload["policy_version"],
    )
    now = datetime.now(timezone.utc)

    first = verify_context_send_payload(payload, policy, cache=cache, now=now)
    payload["ledger_head_id"] = "log-2"
    second = verify_context_send_payload(payload, policy, cache=cache, now=now + timedelta(seconds=30))

    assert first.result == "allow"
    assert second.result == "deny"
    assert second.reason in {"ledger_head_mismatch", "attested_evidence_invalid", "evidence_digest_mismatch"}
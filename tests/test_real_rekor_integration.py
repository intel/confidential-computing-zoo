import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sigstore.models import Bundle

from tc_api.sigstore_baseline import build_baseline_sigstore_bundle
from tc_api.tlog.types import Entry
from tc_api.tlog.local_mr import LocalMRAdapter
from tc_api.tlog_client import TrustedLogAPI
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter
from tc_api.trucon.database import init_db

import importlib


trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")


ENV_RUN = "TC_API_RUN_REAL_REKOR_TESTS"
ENV_TOKEN = "TC_API_REAL_REKOR_IDENTITY_TOKEN"
ENV_REKOR_URL = "TC_API_REAL_REKOR_URL"
ENV_SIGNER_IDENTITY = "TC_API_REAL_REKOR_SIGNER_IDENTITY"


def _require_real_rekor_env() -> tuple[str, str, str | None]:
    if os.getenv(ENV_RUN, "").lower() not in {"1", "true", "yes"}:
        pytest.skip(f"Set {ENV_RUN}=1 to enable the public Rekor smoke test")

    identity_token = os.getenv(ENV_TOKEN)
    if not identity_token:
        pytest.skip(f"Set {ENV_TOKEN} to a valid Sigstore OIDC identity token")

    rekor_url = os.getenv(ENV_REKOR_URL, "https://rekor.sigstore.dev")
    signer_identity = os.getenv(ENV_SIGNER_IDENTITY)
    return identity_token, rekor_url, signer_identity


class MockMRAdapter(LocalMRAdapter):
    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        return "cc" * 48, "bb" * 48


def _make_db_patches(db_path: str):
    names = [
        "insert_record",
        "get_chain_state",
        "update_chain_state",
        "get_record_by_idempotency_key",
        "get_chain_records",
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


@pytest.fixture
def real_rekor_trucon_harness(tmp_path):
    db_path = str(tmp_path / "real-rekor.db")
    init_db(db_path)
    patches = _make_db_patches(db_path)

    old_mr = trucon_app_mod._local_mr
    old_auth = trucon_app_mod._AUTH_DISABLED
    old_tokens = trucon_app_mod._pending_init_tokens.copy()
    old_immutable_log = trucon_app_mod._immutable_log

    try:
        trucon_app_mod._local_mr = MockMRAdapter()
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod.app.state.test_db_path = db_path

        with patch.object(trucon_app_mod, "acquire_instance_lock"), \
             patch.object(trucon_app_mod, "release_instance_lock"), \
             patch.object(trucon_app_mod, "_crash_recovery"), \
             patch.object(trucon_app_mod, "_submit_daemon_loop"), \
             patch.object(trucon_app_mod, "init_db"), \
             patch.object(trucon_app_mod, "insert_record", side_effect=patches["insert_record"]), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "update_chain_state", side_effect=patches["update_chain_state"]), \
             patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=patches["get_record_by_idempotency_key"]), \
             patch.object(trucon_app_mod, "get_chain_records", side_effect=patches["get_chain_records"]), \
             patch.object(trucon_app_mod, "get_latest_confirmed_record", side_effect=patches["get_latest_confirmed_record"]), \
             patch.object(trucon_app_mod, "get_all_chain_ids", side_effect=patches["get_all_chain_ids"]), \
             patch.object(trucon_app_mod, "get_failed_by_chain", side_effect=patches["get_failed_by_chain"]), \
             patch.object(trucon_app_mod, "get_pending_by_chain", side_effect=patches["get_pending_by_chain"]), \
             patch.object(trucon_app_mod, "set_status_submitting", side_effect=patches["set_status_submitting"]), \
             patch.object(trucon_app_mod, "update_record_confirmed", side_effect=patches["update_record_confirmed"]), \
             patch.object(trucon_app_mod, "update_status", side_effect=patches["update_status"]), \
             patch.object(trucon_app_mod, "get_queue_stats", side_effect=patches["get_queue_stats"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client
    finally:
        trucon_app_mod._local_mr = old_mr
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._immutable_log = old_immutable_log
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod._pending_init_tokens.update(old_tokens)


def _request_json_via_testclient(client: TestClient):
    def _request(method: str, path: str, *, json_body=None, **kwargs):
        if method.upper() == "GET":
            response = client.get(path)
        else:
            response = client.post(path, json=json_body)
        if response.status_code >= 400:
            import urllib.error
            import io

            raise urllib.error.HTTPError(path, response.status_code, response.reason_phrase, {}, io.BytesIO(response.content))
        return response.json() if response.content else {}

    return _request


@pytest.mark.integration
def test_public_rekor_round_trip_smoke():
    """Opt-in smoke test for real signing plus public Rekor upload and replay.

    Scope:
    - Uses the real Sigstore signing path from TrustedLogAPI.commit_record()
    - Uploads the resulting bundle to a real Rekor instance
    - Verifies that tc_api replay can retrieve the immutable entry back

        Non-goals:
        - This does not prove multi-entry chain linkage on Rekor, because prev_log_id is
      not currently embedded in the public DSSE payload that replay traverses.
    """

    identity_token, rekor_url, signer_identity = _require_real_rekor_env()

    chain_id = f"rekor-smoke-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    captured: Dict[str, Any] = {}

    tlog = TrustedLogAPI(immutable_log=SigstoreLogAdapter(rekor_url=rekor_url))
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    def _capture_post_to_trucon(**kwargs):
        captured.update(kwargs)
        return {
            "record_id": f"local-{uuid.uuid4().hex[:8]}",
            "sequence_num": 1,
            "mr_value": None,
            "prev_mr_value": None,
        }

    with patch.object(tlog, "_post_to_trucon", side_effect=_capture_post_to_trucon):
        commit_result = tlog.commit_record(
            ctx.record_id,
            event_type="launch",
            event_id=event_id,
            commit_options={"identity_token": identity_token},
        )

    assert commit_result.record_id.startswith("local-")
    bundle_json = captured.get("bundle_json")
    event_digest = captured.get("event_digest")
    assert isinstance(bundle_json, str) and bundle_json
    assert isinstance(event_digest, str) and event_digest.startswith("sha384:")

    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    bundle = Bundle.from_json(bundle_json)
    log_id, status, _receipt = adapter.submit_bundle(bundle)

    assert status == "confirmed"
    assert isinstance(log_id, str) and log_id

    entry = adapter.get_entry(log_id)
    assert entry

    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = tlog.verify_record(log_id, policy=verify_policy)

    assert verify_result.success is True, verify_result.errors
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    assert verify_result.details["entries"][0]["event_id"] == event_id
    assert verify_result.details["entries"][0]["digest"] == event_digest


@pytest.mark.integration
def test_public_rekor_baseline_bundle_round_trip_smoke():
    """Opt-in smoke test for Event Log 0 bundle generation against public Rekor."""

    identity_token, rekor_url, signer_identity = _require_real_rekor_env()

    chain_id = f"rekor-baseline-{uuid.uuid4().hex[:12]}"
    bundle_json, pub_key_pem, event_digest = build_baseline_sigstore_bundle(
        chain_id=chain_id,
        rtmr_value="11" * 48,
        ccel_digest="sha384:" + ("22" * 48),
        identity_token_str=identity_token,
    )

    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    bundle = Bundle.from_json(bundle_json)
    log_id, status, _receipt = adapter.submit_bundle(bundle)

    assert status == "confirmed"
    assert isinstance(log_id, str) and log_id
    assert pub_key_pem.startswith("-----BEGIN PUBLIC KEY-----")

    tlog = TrustedLogAPI(immutable_log=adapter)
    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = tlog.verify_record(log_id, policy=verify_policy)

    assert verify_result.success is True, verify_result.errors
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    assert verify_result.details["entries"][0]["event_id"] == f"evt-log0-{chain_id}"
    assert verify_result.details["entries"][0]["event_type"] == "chain.init"
    assert verify_result.details["entries"][0]["digest"] == event_digest
    predicate_entries = verify_result.details["entries"][0]["predicate_entries"]
    assert any(entry["key"] == "baseline_rtmr" and entry["value"] == "11" * 48 for entry in predicate_entries)
    assert any(entry["key"] == "ccel_digest" and entry["value"] == "sha384:" + ("22" * 48) for entry in predicate_entries)
    assert any(entry["key"] == "pub_key" and entry["value"] == pub_key_pem for entry in predicate_entries)


@pytest.mark.integration
def test_public_rekor_init_chain_submit_verify_baseline_smoke(real_rekor_trucon_harness):
    """Opt-in smoke test for the full explicit baseline path: init_chain -> submit -> verify."""

    identity_token, rekor_url, signer_identity = _require_real_rekor_env()
    chain_id = f"rekor-init-chain-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    with patch("tc_api.sigstore_baseline.Issuer.production") as mock_issuer, \
         patch("tc_api.tlog_client.request_json", side_effect=_request_json_via_testclient(client)):
        mock_issuer.return_value.identity_token.return_value = identity_token
        init_result = tlog.init_chain(chain_id)

    assert init_result is not None
    assert init_result["sequence_num"] == 1

    trucon_app_mod._submit_daemon_tick()

    state = client.get(f"/chain-state/{chain_id}")
    assert state.status_code == 200
    state_data = state.json()
    head_log_id = state_data["head_log_id"]
    assert isinstance(head_log_id, str) and head_log_id

    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = tlog.verify_record(head_log_id, policy=verify_policy)

    assert verify_result.success is True, verify_result.errors
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    entry = verify_result.details["entries"][0]
    assert entry["event_id"] == f"evt-log0-{chain_id}"
    assert entry["event_type"] == "chain.init"
    predicate_entries = entry["predicate_entries"]
    assert any(item["key"] == "baseline_rtmr" and item["value"] == "aa" * 48 for item in predicate_entries)
    assert any(item["key"] == "ccel_digest" and isinstance(item["value"], str) for item in predicate_entries)
    assert any(item["key"] == "pub_key" and item["value"].startswith("-----BEGIN PUBLIC KEY-----") for item in predicate_entries)


@pytest.mark.integration
def test_public_rekor_lazy_workload_baseline_smoke(real_rekor_trucon_harness):
    """Opt-in smoke test for the lazy non-default workload baseline path against public Rekor."""

    identity_token, rekor_url, signer_identity = _require_real_rekor_env()
    chain_id = f"rekor-workload-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    with patch("tc_api.tlog_client.request_json", side_effect=_request_json_via_testclient(client)):
        commit_result = tlog.commit_record(
            ctx.record_id,
            event_type="launch",
            event_id=event_id,
            commit_options={"identity_token": identity_token},
        )

    assert commit_result.record_id
    assert commit_result.event_id == event_id

    trucon_app_mod._submit_daemon_tick()

    records = trucon_db_mod.get_chain_records(chain_id, db_path=client.app.state.test_db_path)
    assert [record["sequence_num"] for record in records] == [1, 2]
    baseline_record = records[0]
    event_record = records[1]
    assert baseline_record["event_id"] == f"evt-log0-{chain_id}"
    assert event_record["event_id"] == event_id
    assert baseline_record["status"] == "CONFIRMED"
    assert event_record["status"] == "CONFIRMED"
    assert isinstance(baseline_record["log_id"], str) and baseline_record["log_id"]

    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = tlog.verify_record(baseline_record["log_id"], policy=verify_policy)

    assert verify_result.success is True, verify_result.errors
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    entry = verify_result.details["entries"][0]
    assert entry["event_id"] == f"evt-log0-{chain_id}"
    assert entry["event_type"] == "chain.init"
    predicate_entries = entry["predicate_entries"]
    assert any(item["key"] == "baseline_rtmr" and item["value"] == "aa" * 48 for item in predicate_entries)
    assert any(item["key"] == "ccel_digest" and isinstance(item["value"], str) for item in predicate_entries)
    assert any(item["key"] == "pub_key" and item["value"].startswith("-----BEGIN PUBLIC KEY-----") for item in predicate_entries)


@pytest.mark.integration
def test_public_rekor_multi_entry_predecessor_proof_uses_candidate_discovery(real_rekor_trucon_harness):
    """Opt-in smoke test for multi-entry predecessor proof against public Rekor.

    This test clears the adapter's process-local bundle cache before replay so the
    verified predecessor proof must come from public payload-hash candidate discovery
    and normalized entry matching rather than cache adjacency alone.
    """

    identity_token, rekor_url, signer_identity = _require_real_rekor_env()
    chain_id = f"rekor-predecessor-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    with patch("tc_api.tlog_client.request_json", side_effect=_request_json_via_testclient(client)):
        commit_result = tlog.commit_record(
            ctx.record_id,
            event_type="launch",
            event_id=event_id,
            commit_options={"identity_token": identity_token},
        )

    assert commit_result.record_id
    trucon_app_mod._submit_daemon_tick()

    records = trucon_db_mod.get_chain_records(chain_id, db_path=client.app.state.test_db_path)
    assert [record["sequence_num"] for record in records] == [1, 2]
    head_record = records[1]
    assert head_record["event_id"] == event_id
    assert head_record["status"] == "CONFIRMED"
    assert isinstance(head_record["log_id"], str) and head_record["log_id"]

    SigstoreLogAdapter._bundle_entry_cache.clear()
    replay_adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    replay_tlog = TrustedLogAPI(immutable_log=replay_adapter)

    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = replay_tlog.verify_record(head_record["log_id"], policy=verify_policy)

    assert verify_result.success is True, verify_result.errors
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    entry = verify_result.details["entries"][0]
    assert entry["event_id"] == event_id
    assert entry["predecessor_ok"] is True
    assert entry["predecessor_status"] == "proven"
    assert entry["candidate_count"] >= 1
    assert entry["materialized_candidate_count"] >= 1
    assert entry["matched_candidate_count"] == 1

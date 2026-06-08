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

import os
import uuid
import json
import hashlib
from contextlib import ExitStack
from datetime import datetime, timezone
from typing import Any, Dict, Tuple
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sigstore.models import Bundle
from sigstore.oidc import IdentityToken as SigstoreIdentityToken

import tc_api.identity.sigstore_baseline as sigstore_baseline_mod
from tc_api.identity.sigstore_baseline import build_baseline_sigstore_bundle
from tlog.types import Entry
from tlog.local_mr import LocalMRAdapter
import tc_api.transparency.verification as tlog_client_mod
from tc_api.transparency.commit_client import TrustedLogAPI
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from tlog.backends.rekor.oci_mirror import OciBundleMirror
from tc_api.trucon.database import init_db
from tc_api.cli.verify import main as verify_main
from tests.test_real_oci_mirror_integration import real_oci_registry_runtime  # noqa: F401
from tests.utils import make_db_patches

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


@pytest.fixture(scope="module")
def real_rekor_runtime():
    identity_token, rekor_url, signer_identity = _require_real_rekor_env()
    return {
        "identity_token": identity_token,
        "rekor_url": rekor_url,
        "signer_identity": signer_identity,
        "cached_identity_token": SigstoreIdentityToken(identity_token),
    }


@pytest.fixture(autouse=True)
def reuse_real_rekor_identity_token(real_rekor_runtime):
    raw_token = real_rekor_runtime["identity_token"]
    cached_token = real_rekor_runtime["cached_identity_token"]
    original_identity_token_ctor = tlog_client_mod.IdentityToken
    original_resolve_identity_token = sigstore_baseline_mod._resolve_identity_token

    def _resolve_cached_identity_token(identity_token_str=None):
        if identity_token_str in (None, raw_token):
            return cached_token
        return original_resolve_identity_token(identity_token_str)

    def _parse_cached_identity_token(identity_token_str):
        if identity_token_str == raw_token:
            return cached_token
        return original_identity_token_ctor(identity_token_str)

    with patch.object(tlog_client_mod, "IdentityToken", side_effect=_parse_cached_identity_token), \
         patch.object(sigstore_baseline_mod, "_resolve_identity_token", side_effect=_resolve_cached_identity_token):
        yield


class MockMRAdapter(LocalMRAdapter):
    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        prev_mr = self.read(index)
        digest_hex = digest.removeprefix("sha384:")
        next_mr = hashlib.sha384(bytes.fromhex(prev_mr) + bytes.fromhex(digest_hex)).hexdigest()
        return next_mr, prev_mr


@pytest.fixture
def real_rekor_trucon_harness(tmp_path):
    db_path = str(tmp_path / "real-rekor.db")
    init_db(db_path)
    patches = make_db_patches(
        trucon_db_mod,
        db_path,
        [
            "insert_record",
            "get_chain_state",
            "update_chain_state",
            "create_commit_intent",
            "get_active_commit_intent_for_chain",
            "get_commit_intent_by_idempotency_key",
            "get_commit_intent_by_token",
            "update_commit_intent_status",
            "expire_active_commit_intents",
            "get_record_by_id",
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
            "enqueue_mirror_publish",
            "get_pending_mirror_publishes",
            "update_mirror_publish_status",
            "get_mirror_publish_job",
        ],
    )

    old_mr = trucon_app_mod._local_mr
    old_auth = trucon_app_mod._AUTH_DISABLED
    old_tokens = trucon_app_mod._pending_init_tokens.copy()
    old_immutable_log = trucon_app_mod._immutable_log
    old_bundle_mirror = trucon_app_mod._bundle_mirror

    try:
        trucon_app_mod._local_mr = MockMRAdapter()
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod.app.state.test_db_path = db_path

        with ExitStack() as stack:
            stack.enter_context(patch.object(trucon_app_mod, "acquire_instance_lock"))
            stack.enter_context(patch.object(trucon_app_mod, "release_instance_lock"))
            stack.enter_context(patch.object(trucon_app_mod, "_crash_recovery"))
            stack.enter_context(patch.object(trucon_app_mod, "_submit_daemon_loop"))
            stack.enter_context(patch.object(trucon_app_mod, "init_db"))
            stack.enter_context(patch.object(trucon_app_mod, "insert_record", side_effect=patches["insert_record"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_chain_state", side_effect=patches["update_chain_state"]))
            stack.enter_context(patch.object(trucon_app_mod, "create_commit_intent", side_effect=patches["create_commit_intent"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_active_commit_intent_for_chain", side_effect=patches["get_active_commit_intent_for_chain"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_commit_intent_by_idempotency_key", side_effect=patches["get_commit_intent_by_idempotency_key"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_commit_intent_by_token", side_effect=patches["get_commit_intent_by_token"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_commit_intent_status", side_effect=patches["update_commit_intent_status"]))
            stack.enter_context(patch.object(trucon_app_mod, "expire_active_commit_intents", side_effect=patches["expire_active_commit_intents"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_record_by_id", side_effect=patches["get_record_by_id"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=patches["get_record_by_idempotency_key"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_chain_records", side_effect=patches["get_chain_records"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_latest_confirmed_record", side_effect=patches["get_latest_confirmed_record"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_all_chain_ids", side_effect=patches["get_all_chain_ids"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_failed_by_chain", side_effect=patches["get_failed_by_chain"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_pending_by_chain", side_effect=patches["get_pending_by_chain"]))
            stack.enter_context(patch.object(trucon_app_mod, "set_status_submitting", side_effect=patches["set_status_submitting"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_record_confirmed", side_effect=patches["update_record_confirmed"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_status", side_effect=patches["update_status"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_queue_stats", side_effect=patches["get_queue_stats"]))
            stack.enter_context(patch.object(trucon_app_mod, "enqueue_mirror_publish", side_effect=patches["enqueue_mirror_publish"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_pending_mirror_publishes", side_effect=patches["get_pending_mirror_publishes"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_mirror_publish_status", side_effect=patches["update_mirror_publish_status"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_mirror_publish_job", side_effect=patches["get_mirror_publish_job"]))
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client
    finally:
        trucon_app_mod._local_mr = old_mr
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._immutable_log = old_immutable_log
        trucon_app_mod._bundle_mirror = old_bundle_mirror
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


def _fetch_trucon_json_via_testclient(client: TestClient):
    request = _request_json_via_testclient(client)

    def _fetch(path: str):
        return request("GET", path)

    return _fetch


@pytest.mark.integration
def test_public_rekor_round_trip_smoke(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for real signing plus public Rekor upload and replay.

    Scope:
    - Uses the real Sigstore signing path from TrustedLogAPI.commit_record()
    - Uploads the resulting bundle to a real Rekor instance
    - Verifies that tc_api replay can retrieve the immutable entry back

        Non-goals:
        - This does not prove multi-entry chain linkage on Rekor, because prev_log_id is
      not currently embedded in the public DSSE payload that replay traverses.
    """

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    client = real_rekor_trucon_harness
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    trucon_app_mod._immutable_log = adapter

    chain_id = f"rekor-smoke-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    captured: Dict[str, Any] = {}

    tlog = TrustedLogAPI(immutable_log=adapter)
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

    with patch.object(tlog, "_post_to_trucon", side_effect=_capture_post_to_trucon), \
         patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
        commit_result = tlog.commit_record(
            ctx.record_id,
            event_type="launch",
            event_id=event_id,
            commit_options={"identity_token": identity_token},
        )

    # commit_record() triggers lazy init_chain() for non-default chains, but the baseline
    # still needs the submit daemon tick before its Rekor predecessor can be replayed.
    trucon_app_mod._submit_daemon_tick()

    assert commit_result.record_id.startswith("local-")
    bundle_json = captured.get("bundle_json")
    event_digest = captured.get("event_digest")
    assert isinstance(bundle_json, str) and bundle_json
    assert isinstance(event_digest, str) and event_digest.startswith("sha384:")

    bundle = Bundle.from_json(bundle_json)
    log_id, status, _receipt = adapter.submit_bundle(bundle)

    assert status == "confirmed"
    assert isinstance(log_id, str) and log_id

    entry = adapter.get_entry(log_id)
    assert entry

    normalized_entry = tlog_client_mod._normalize_verification_entry(entry, 1, signer_identity)

    # This smoke test only proves real signing, Rekor upload, and entry retrieval for the
    # current node. It intentionally does not require predecessor continuity, which depends
    # on whether public Rekor can materialize historical DSSE predicate fields.
    assert normalized_entry["chain_id"] == chain_id
    assert normalized_entry["event_id"] == event_id
    assert normalized_entry["digest"] == event_digest
    assert normalized_entry["event_type"] == "launch"
    if signer_identity:
        assert normalized_entry["signer_identity_match"] is True


@pytest.mark.integration
def test_public_rekor_intoto_round_trip_materializes_attestation_payload(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for the intoto upload path and attestation-backed replay materialization."""

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    client = real_rekor_trucon_harness
    adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="intoto")
    trucon_app_mod._immutable_log = adapter

    chain_id = f"rekor-intoto-smoke-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    captured: Dict[str, Any] = {}

    tlog = TrustedLogAPI(immutable_log=adapter)
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

    with patch.object(tlog, "_post_to_trucon", side_effect=_capture_post_to_trucon), \
         patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
        commit_result = tlog.commit_record(
            ctx.record_id,
            event_type="launch",
            event_id=event_id,
            commit_options={"identity_token": identity_token},
        )

    trucon_app_mod._submit_daemon_tick()

    assert commit_result.record_id.startswith("local-")
    bundle = Bundle.from_json(captured["bundle_json"])
    log_id, status, _receipt = adapter.submit_bundle(bundle)

    assert status == "confirmed"
    assert isinstance(log_id, str) and log_id

    SigstoreLogAdapter._bundle_entry_cache.clear()
    replay_adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="intoto")
    entry = replay_adapter.get_entry(log_id)
    normalized_entry = tlog_client_mod._normalize_verification_entry(entry, 1, signer_identity)

    assert normalized_entry["chain_id"] == chain_id
    assert normalized_entry["event_id"] == event_id
    assert normalized_entry["digest"] == captured["event_digest"]
    assert normalized_entry["event_type"] == "launch"
    assert normalized_entry["replay_provenance"] == "attestation-storage"
    if signer_identity:
        assert normalized_entry["signer_identity_match"] is True


@pytest.mark.integration
def test_public_rekor_baseline_bundle_round_trip_smoke(real_rekor_runtime):
    """Opt-in smoke test for Event Log 0 bundle generation against public Rekor."""

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]

    chain_id = f"rekor-baseline-{uuid.uuid4().hex[:12]}"
    bundle_json, pub_key_pem, event_digest = build_baseline_sigstore_bundle(
        chain_id=chain_id,
        rtmr_value="11" * 48,
        ccel_digest="sha384:" + ("22" * 48),
        ccel_eventlog_b64="Zm9v",
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
    assert verify_result.details["entries"][0]["predecessor_status"] == "origin"
    assert verify_result.details["entries"][0]["digest"] == event_digest
    predicate_entries = verify_result.details["entries"][0]["predicate_entries"]
    assert any(entry["key"] == "baseline_rtmr" and entry["value"] == "11" * 48 for entry in predicate_entries)
    assert any(entry["key"] == "ccel_eventlog_b64" and entry["value"] == "Zm9v" for entry in predicate_entries)
    assert any(entry["key"] == "pub_key" and entry["value"] == pub_key_pem for entry in predicate_entries)


@pytest.mark.integration
def test_public_rekor_init_chain_submit_verify_baseline_smoke(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for the full explicit baseline path: init_chain -> submit -> verify."""

    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    chain_id = f"rekor-init-chain-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
        init_result = tlog.init_chain(chain_id)

    assert init_result is not None
    assert init_result["sequence_num"] == 1

    trucon_app_mod._submit_daemon_tick()

    state = client.get("/chain-state")
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
    assert entry["predecessor_status"] == "origin"
    predicate_entries = entry["predicate_entries"]
    assert any(item["key"] == "baseline_rtmr" and item["value"] == "aa" * 48 for item in predicate_entries)
    assert any(item["key"] == "ccel_eventlog_b64" and isinstance(item["value"], str) for item in predicate_entries)
    assert any(item["key"] == "pub_key" and item["value"].startswith("-----BEGIN PUBLIC KEY-----") for item in predicate_entries)


@pytest.mark.integration
def test_public_rekor_lazy_workload_baseline_smoke(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for the lazy non-default workload baseline path against public Rekor."""

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    chain_id = f"rekor-workload-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
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
    assert entry["predecessor_status"] == "origin"
    predicate_entries = entry["predicate_entries"]
    assert any(item["key"] == "baseline_rtmr" and item["value"] == "aa" * 48 for item in predicate_entries)
    assert any(item["key"] == "ccel_eventlog_b64" and isinstance(item["value"], str) for item in predicate_entries)
    assert any(item["key"] == "pub_key" and item["value"].startswith("-----BEGIN PUBLIC KEY-----") for item in predicate_entries)


@pytest.mark.integration
def test_public_rekor_multi_entry_predecessor_proof_reports_public_replay_limit(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for the current public-Rekor replay limit on DSSE entries.

    Rekor v1 persists DSSE entries as canonicalized bodies with payloadHash/envelopeHash,
    not the original in-toto payload. After clearing process-local caches, tc_api can still
    discover predecessor candidates publicly, but it cannot reconstruct verifier-critical
    predicate fields such as sequence_num/prev_event_digest from the public entry alone.
    """

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    chain_id = f"rekor-predecessor-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="dsse")
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
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
    replay_adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="dsse")
    replay_tlog = TrustedLogAPI(immutable_log=replay_adapter)

    verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
    if signer_identity:
        verify_policy["signer_identity"] = signer_identity

    verify_result = replay_tlog.verify_record(head_record["log_id"], policy=verify_policy)

    assert verify_result.success is False
    assert verify_result.errors == ["Signed predecessor continuity verification failed"]
    assert verify_result.details["chain_id"] == chain_id
    assert verify_result.details["entry_count"] == 1
    entry = verify_result.details["entries"][0]
    assert entry["predecessor_ok"] is False
    assert entry["predecessor_status"] == "unsupported"
    assert entry["public_history_status"] == "unmaterialized"


@pytest.mark.integration
def test_public_rekor_intoto_multi_entry_predecessor_proof_without_mirror(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for intoto predecessor proof through public Rekor plus attestation storage alone."""

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    chain_id = f"rekor-intoto-predecessor-{uuid.uuid4().hex[:12]}"
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="intoto")
    client = real_rekor_trucon_harness
    trucon_app_mod._immutable_log = adapter

    tlog = TrustedLogAPI(immutable_log=adapter)
    ctx = tlog.init_record(context={"chain_ref": chain_id})
    tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
    tlog.add_entry(ctx.record_id, Entry(key="timestamp_hint", value=datetime.now(timezone.utc).isoformat()))

    with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
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
    replay_adapter = SigstoreLogAdapter(rekor_url=rekor_url, rekor_entry_type="intoto")
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
    assert entry["history_materialization_provenance"] == "attestation-storage"
    assert entry["public_history_status"] == "public"


@pytest.mark.integration
def test_public_rekor_multi_chain_replay_keeps_chain_histories_isolated(real_rekor_runtime, real_rekor_trucon_harness):
    """Opt-in smoke test for replay isolation across two chains on the same Rekor service.

    Even when public replay cannot reconstruct predecessor contracts from canonicalized DSSE
    bodies alone, the verifier must still stay scoped to the requested chain_id and avoid
    cross-chain bleed when multiple chains share the same signer and Rekor backend.
    """

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    client = real_rekor_trucon_harness
    adapter = SigstoreLogAdapter(rekor_url=rekor_url)
    trucon_app_mod._immutable_log = adapter

    committed_heads: list[tuple[str, str, str]] = []
    for suffix in ("a", "b"):
        chain_id = f"rekor-multi-chain-{suffix}-{uuid.uuid4().hex[:10]}"
        event_id = f"evt-{suffix}-{uuid.uuid4().hex[:10]}"
        tlog = TrustedLogAPI(immutable_log=adapter)
        ctx = tlog.init_record(context={"chain_ref": chain_id})
        tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
        tlog.add_entry(ctx.record_id, Entry(key="chain_marker", value=chain_id))

        with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
            commit_result = tlog.commit_record(
                ctx.record_id,
                event_type="launch",
                event_id=event_id,
                commit_options={"identity_token": identity_token},
            )

        assert commit_result.record_id
        committed_heads.append((chain_id, event_id, commit_result.record_id))

    trucon_app_mod._submit_daemon_tick()

    resolved_heads: list[tuple[str, str, str]] = []
    for chain_id, event_id, record_id in committed_heads:
        records = trucon_db_mod.get_chain_records(chain_id, db_path=client.app.state.test_db_path)
        assert [record["sequence_num"] for record in records] == [1, 2]
        head_record = next(record for record in records if record["record_id"] == record_id)
        assert head_record["event_id"] == event_id
        assert head_record["status"] == "CONFIRMED"
        assert isinstance(head_record["log_id"], str) and head_record["log_id"]
        resolved_heads.append((chain_id, event_id, head_record["log_id"]))

    SigstoreLogAdapter._bundle_entry_cache.clear()
    replay_adapter = SigstoreLogAdapter(rekor_url=rekor_url)

    for chain_id, event_id, head_log_id in resolved_heads:
        replay_tlog = TrustedLogAPI(immutable_log=replay_adapter)
        verify_policy: Dict[str, Any] = {"chain_id": chain_id, "expected_entry_count": 1}
        if signer_identity:
            verify_policy["signer_identity"] = signer_identity

        verify_result = replay_tlog.verify_record(head_log_id, policy=verify_policy)

        assert verify_result.success is False
        assert verify_result.errors == ["Signed predecessor continuity verification failed"]
        assert verify_result.details["chain_id"] == chain_id
        assert verify_result.details["entry_count"] == 1
        entry = verify_result.details["entries"][0]
        assert entry["event_id"] in {event_id, None}
        assert entry["predecessor_ok"] is False
        assert entry["predecessor_status"] == "unsupported"
        assert entry["public_history_status"] == "unmaterialized"


@pytest.mark.integration
def test_public_rekor_real_oci_multi_chain_verify_smoke(
    real_rekor_runtime,
    real_rekor_trucon_harness,
    real_oci_registry_runtime,
    capsys,
):
    """Opt-in smoke test for real Rekor, real OCI mirror publication, and real verify across two chains."""

    identity_token = real_rekor_runtime["identity_token"]
    rekor_url = real_rekor_runtime["rekor_url"]
    signer_identity = real_rekor_runtime["signer_identity"]
    client = real_rekor_trucon_harness
    mirror_location = f"{real_oci_registry_runtime['base_url']}/{real_oci_registry_runtime['repository']}"
    bundle_mirror = OciBundleMirror(mirror_location)
    adapter = SigstoreLogAdapter(rekor_url=rekor_url, bundle_mirror=bundle_mirror)
    trucon_app_mod._immutable_log = adapter
    old_bundle_mirror = trucon_app_mod._bundle_mirror
    trucon_app_mod._bundle_mirror = bundle_mirror

    committed_heads: list[tuple[str, str, str]] = []
    try:
        for suffix in ("a", "b"):
            chain_id = f"rekor-oci-verify-{suffix}-{uuid.uuid4().hex[:10]}"
            event_id = f"evt-{suffix}-{uuid.uuid4().hex[:10]}"
            tlog = TrustedLogAPI(immutable_log=adapter)
            ctx = tlog.init_record(context={"chain_ref": chain_id})
            tlog.add_entry(ctx.record_id, Entry(key="operation_result", value="success"))
            tlog.add_entry(ctx.record_id, Entry(key="chain_marker", value=chain_id))

            with patch("tc_api.transparency.commit_client.request_json", side_effect=_request_json_via_testclient(client)):
                commit_result = tlog.commit_record(
                    ctx.record_id,
                    event_type="launch",
                    event_id=event_id,
                    commit_options={"identity_token": identity_token},
                )

            assert commit_result.record_id
            committed_heads.append((chain_id, event_id, commit_result.record_id))

        trucon_app_mod._submit_daemon_tick()
        SigstoreLogAdapter._bundle_entry_cache.clear()

        for chain_id, event_id, record_id in committed_heads:
            records = trucon_db_mod.get_chain_records(chain_id, db_path=client.app.state.test_db_path)
            assert [record["sequence_num"] for record in records] == [1, 2]
            head_record = next(record for record in records if record["record_id"] == record_id)
            assert head_record["status"] == "CONFIRMED"
            assert isinstance(head_record["log_id"], str) and head_record["log_id"]

            argv = [
                chain_id,
                "--troubleshoot-live",
                "--json",
                "--mirror-dir",
                mirror_location,
                "--require-mirror",
            ]
            if signer_identity:
                argv.extend(["--signer-identity", signer_identity])

            with patch("tc_api.cli.verify._fetch_trucon_json", side_effect=_fetch_trucon_json_via_testclient(client)):
                exit_code = verify_main(argv)

            rendered = json.loads(capsys.readouterr().out)
            assert exit_code == 0, rendered
            assert rendered["target"]["chain_id"] == chain_id
            assert rendered["summary"]["status"] == "verified"
            assert rendered["summary"]["verification_tier"] == "public+mirrored"
            assert rendered["diagnostics"]["replay"]["provenance_status"] == "mirrored"
            assert rendered["diagnostics"]["replay"]["first_entry_issue"] is None
            assert rendered["diagnostics"]["fallback"]["valid"] is True
            assert rendered["replay"]["provenance"]["status"] == "mirrored"
            assert rendered["replay"]["entry_count"] == 1
            assert rendered["entries"][0]["event_id"] == event_id
            assert rendered["entries"][0]["predecessor_status"] == "proven"
            assert rendered["entries"][0]["history_materialization_provenance"] == "mirror"
            assert rendered["fallback"]["reachable"] is True
            assert rendered["fallback"]["valid"] is True
    finally:
        trucon_app_mod._bundle_mirror = old_bundle_mirror

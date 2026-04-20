"""
Tests for TruCon /init-chain endpoints (Event Log 0 baseline).
"""

import importlib
import os
import pytest
from unittest.mock import patch, MagicMock
from typing import Tuple

from fastapi.testclient import TestClient
from tc_api.tlog.local_mr import LocalMRAdapter
from tc_api.trucon.database import init_db

trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")


class MockMRAdapter(LocalMRAdapter):
    """Mock MR adapter that returns deterministic values."""

    def read(self, index: int) -> str:
        return "aa" * 48  # 96-char hex = 384-bit SHA-384

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        return "cc" * 48, "bb" * 48


def _make_db_patches(db_path: str):
    """Create patched versions of DB functions that use the test db_path."""
    orig_insert = trucon_db_mod.insert_record
    orig_get_chain_state = trucon_db_mod.get_chain_state
    orig_update_chain_state = trucon_db_mod.update_chain_state
    orig_get_record_by_idem = trucon_db_mod.get_record_by_idempotency_key
    orig_get_chain_records = trucon_db_mod.get_chain_records

    def patched_insert(*args, **kwargs):
        kwargs.setdefault("db_path", db_path)
        return orig_insert(*args, **kwargs)

    def patched_get_chain_state(*args, **kwargs):
        kwargs.setdefault("db_path", db_path)
        return orig_get_chain_state(*args, **kwargs)

    def patched_update_chain_state(*args, **kwargs):
        kwargs.setdefault("db_path", db_path)
        return orig_update_chain_state(*args, **kwargs)

    def patched_get_record_by_idem(*args, **kwargs):
        kwargs.setdefault("db_path", db_path)
        return orig_get_record_by_idem(*args, **kwargs)

    def patched_get_chain_records(*args, **kwargs):
        kwargs.setdefault("db_path", db_path)
        return orig_get_chain_records(*args, **kwargs)

    return {
        "insert_record": patched_insert,
        "get_chain_state": patched_get_chain_state,
        "update_chain_state": patched_update_chain_state,
        "get_record_by_idempotency_key": patched_get_record_by_idem,
        "get_chain_records": patched_get_chain_records,
    }


@pytest.fixture
def trucon_client(tmp_path):
    """Set up an isolated TruCon TestClient with mock adapters and temp DB."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    patches = _make_db_patches(db_path)

    old_mr = trucon_app_mod._local_mr
    old_auth = trucon_app_mod._AUTH_DISABLED
    old_tokens = trucon_app_mod._pending_init_tokens.copy()

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
             patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
             patch.object(trucon_app_mod, "insert_record", side_effect=patches["insert_record"]), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "update_chain_state", side_effect=patches["update_chain_state"]), \
             patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=patches["get_record_by_idempotency_key"]), \
             patch.object(trucon_app_mod, "get_chain_records", side_effect=patches["get_chain_records"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client
    finally:
        trucon_app_mod._local_mr = old_mr
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod._pending_init_tokens.update(old_tokens)


@pytest.fixture
def trucon_client_no_tee(tmp_path):
    """TruCon TestClient with no TEE (non-TEE mode, _local_mr=None)."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    patches = _make_db_patches(db_path)

    old_mr = trucon_app_mod._local_mr
    old_auth = trucon_app_mod._AUTH_DISABLED
    old_tokens = trucon_app_mod._pending_init_tokens.copy()

    try:
        trucon_app_mod._local_mr = None
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod.app.state.test_db_path = db_path

        with patch.object(trucon_app_mod, "acquire_instance_lock"), \
             patch.object(trucon_app_mod, "release_instance_lock"), \
             patch.object(trucon_app_mod, "_crash_recovery"), \
             patch.object(trucon_app_mod, "_submit_daemon_loop"), \
             patch.object(trucon_app_mod, "init_db"), \
             patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
             patch.object(trucon_app_mod, "insert_record", side_effect=patches["insert_record"]), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "update_chain_state", side_effect=patches["update_chain_state"]), \
             patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=patches["get_record_by_idempotency_key"]), \
             patch.object(trucon_app_mod, "get_chain_records", side_effect=patches["get_chain_records"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client
    finally:
        trucon_app_mod._local_mr = old_mr
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod._pending_init_tokens.update(old_tokens)


class TestGetBaseline:
    """Tests for GET /init-chain/{chain_id}/baseline."""

    def test_baseline_success(self, trucon_client):
        resp = trucon_client.get("/init-chain/test-chain/baseline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rtmr_value"] == "aa" * 48
        assert data["init_token"]
        assert len(data["init_token"]) > 0

    def test_baseline_returns_ccel_digest(self, trucon_client):
        with patch.object(trucon_app_mod, "compute_ccel_digest", return_value="sha384:bb" + "cc" * 47):
            resp = trucon_client.get("/init-chain/test-chain/baseline")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ccel_digest"] == "sha384:bb" + "cc" * 47

    def test_baseline_non_tee_mode(self, trucon_client_no_tee):
        resp = trucon_client_no_tee.get("/init-chain/test-chain/baseline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rtmr_value"] is None
        assert data["init_token"]

    def test_baseline_chain_already_exists_409(self, trucon_client):
        # First, successfully init a chain
        resp1 = trucon_client.get("/init-chain/my-chain/baseline")
        assert resp1.status_code == 200
        token = resp1.json()["init_token"]

        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "my-chain",
            "init_token": token,
            "signed_bundle": '{"payloadType":"application/vnd.dsse+json"}',
            "pub_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        })
        assert resp2.status_code == 200

        # Now GET baseline for same chain should return 409
        resp3 = trucon_client.get("/init-chain/my-chain/baseline")
        assert resp3.status_code == 409

    def test_baseline_unique_tokens(self, trucon_client):
        resp1 = trucon_client.get("/init-chain/chain-a/baseline")
        resp2 = trucon_client.get("/init-chain/chain-b/baseline")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["init_token"] != resp2.json()["init_token"]


class TestPostInitChain:
    """Tests for POST /init-chain."""

    def test_init_chain_success(self, trucon_client):
        # Phase 1: get baseline
        resp1 = trucon_client.get("/init-chain/test-chain/baseline")
        assert resp1.status_code == 200
        token = resp1.json()["init_token"]

        # Phase 2: init chain
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token,
            "signed_bundle": '{"payloadType":"application/vnd.dsse+json"}',
            "pub_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        })
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["record_id"]
        assert data["sequence_num"] == 1

    def test_init_chain_invalid_token_400(self, trucon_client):
        resp = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": "bogus-token-that-does-not-exist",
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    def test_init_chain_token_mismatch_400(self, trucon_client):
        # Get token for chain-a
        resp1 = trucon_client.get("/init-chain/chain-a/baseline")
        token = resp1.json()["init_token"]

        # Try to use it for chain-b
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "chain-b",
            "init_token": token,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp2.status_code == 400
        assert "mismatch" in resp2.json()["detail"]

    def test_init_chain_double_init_409(self, trucon_client):
        # Init chain once
        resp1 = trucon_client.get("/init-chain/test-chain/baseline")
        token1 = resp1.json()["init_token"]
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token1,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200

        # Get another token (should fail at GET since chain exists)
        resp3 = trucon_client.get("/init-chain/test-chain/baseline")
        assert resp3.status_code == 409

    def test_init_chain_token_consumed(self, trucon_client):
        """init_token is single-use — replaying it should fail."""
        resp1 = trucon_client.get("/init-chain/test-chain/baseline")
        token = resp1.json()["init_token"]

        # First use succeeds
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200

        # Second use fails (token consumed)
        resp3 = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp3.status_code == 400

    def test_commit_after_init_gets_sequence_2(self, trucon_client):
        """After init-chain, the next /commit should get sequence_num=2."""
        # Init chain
        resp1 = trucon_client.get("/init-chain/test-chain/baseline")
        token = resp1.json()["init_token"]
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200
        assert resp2.json()["sequence_num"] == 1

        # Commit should get sequence_num=2
        resp3 = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": "test-chain",
            "event_digest": "sha384:" + "ab" * 48,
        })
        assert resp3.status_code == 200
        assert resp3.json()["sequence_num"] == 2

    def test_init_chain_non_tee_mode(self, trucon_client_no_tee):
        """Init chain works in non-TEE mode with null RTMR."""
        resp1 = trucon_client_no_tee.get("/init-chain/test-chain/baseline")
        assert resp1.status_code == 200
        assert resp1.json()["rtmr_value"] is None
        token = resp1.json()["init_token"]

        resp2 = trucon_client_no_tee.post("/init-chain", json={
            "chain_id": "test-chain",
            "init_token": token,
            "signed_bundle": "{}",
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200
        assert resp2.json()["sequence_num"] == 1


class TestLazyWorkloadBaseline:
    def test_first_workload_commit_auto_creates_baseline(self, trucon_client):
        resp = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": "workload-a",
            "event_digest": "sha384:" + "ab" * 48,
        })
        assert resp.status_code == 200
        assert resp.json()["sequence_num"] == 2

        records = trucon_db_mod.get_chain_records("workload-a", db_path=trucon_client.app.state.test_db_path)
        assert len(records) == 2
        assert records[0]["event_id"] == "evt-log0-workload-a"
        assert records[0]["sequence_num"] == 1
        assert records[1]["sequence_num"] == 2

    def test_concurrent_first_workload_commits_create_single_baseline(self, trucon_client):
        import concurrent.futures

        def do_commit(event_suffix: str):
            return trucon_client.post("/commit", json={
                "bundle": '{"payloadType":"test"}',
                "chain_id": "workload-race",
                "event_digest": "sha384:" + event_suffix * 96,
                "event_id": f"evt-{event_suffix}",
            })

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(do_commit, "a"), executor.submit(do_commit, "b")]
            responses = [future.result() for future in futures]

        assert {response.status_code for response in responses} == {200}
        assert sorted(response.json()["sequence_num"] for response in responses) == [2, 3]

        records = trucon_db_mod.get_chain_records("workload-race", db_path=trucon_client.app.state.test_db_path)
        assert [record["sequence_num"] for record in records] == [1, 2, 3]
        assert sum(1 for record in records if record["event_id"] == "evt-log0-workload-race") == 1

    def test_lazy_baseline_failure_rejects_first_business_event(self, trucon_client):
        with patch.object(trucon_app_mod, "compute_ccel_digest", side_effect=RuntimeError("ccel boom")):
            resp = trucon_client.post("/commit", json={
                "bundle": '{"payloadType":"test"}',
                "chain_id": "workload-fail",
                "event_digest": "sha384:" + "ab" * 48,
            })

        assert resp.status_code == 500
        records = trucon_db_mod.get_chain_records("workload-fail", db_path=trucon_client.app.state.test_db_path)
        assert records == []

    def test_verify_chain_rejects_non_default_without_baseline(self, trucon_client_no_tee):
        trucon_db_mod.insert_record(
            record_id="rec-1",
            event_id="evt-1",
            payload={"bundle": "test", "chain_id": "workload-no-baseline"},
            status="CONFIRMED",
            chain_id="workload-no-baseline",
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=None,
            sequence_num=1,
            event_digest="sha384:" + "ab" * 48,
            db_path=trucon_client_no_tee.app.state.test_db_path,
        )

        resp = trucon_client_no_tee.get("/verify-chain/workload-no-baseline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
        assert data["entries"][0]["error"] == "non-default chain 'workload-no-baseline' does not begin with Event Log 0"

    def test_verify_chain_accepts_pending_baseline_origin(self, trucon_client_no_tee):
        trucon_db_mod.insert_record(
            record_id="rec-log0",
            event_id="evt-log0-workload-pending",
            payload={"bundle": "test", "chain_id": "workload-pending", "is_baseline": True},
            status="PENDING",
            chain_id="workload-pending",
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=None,
            sequence_num=1,
            event_digest=None,
            db_path=trucon_client_no_tee.app.state.test_db_path,
        )
        trucon_db_mod.insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test", "chain_id": "workload-pending"},
            status="PENDING",
            chain_id="workload-pending",
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=None,
            sequence_num=2,
            event_digest="sha384:" + "ab" * 48,
            db_path=trucon_client_no_tee.app.state.test_db_path,
        )

        resp = trucon_client_no_tee.get("/verify-chain/workload-pending")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"][0]["error"] is None
        assert data["rekor_pending"] == 2

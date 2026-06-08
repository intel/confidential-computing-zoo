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

"""
Tests for TruCon /init-chain endpoints (Event Log 0 baseline).
"""

import importlib
import json
from contextlib import ExitStack
import pytest
from unittest.mock import patch
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from fastapi.testclient import TestClient
from tlog.local_mr import LocalMRAdapter
from tc_api.trucon.database import init_db
from tc_api.trucon.owner_authorization import sign_owner_authorization
from tests.utils import EchoQuoteAdapter, make_db_patches

trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")

DEFAULT_CHAIN_ID = "default"


class MockMRAdapter(LocalMRAdapter):
    """Mock MR adapter that returns deterministic values."""

    def read(self, index: int) -> str:
        return "aa" * 48  # 96-char hex = 384-bit SHA-384

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        return "cc" * 48, "bb" * 48


@pytest.fixture
def trucon_client(tmp_path):
    """Set up an isolated TruCon TestClient with mock adapters and temp DB."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)

    patches = make_db_patches(
        trucon_db_mod,
        db_path,
        [
            "insert_record",
            "get_chain_state",
            "update_chain_state",
            "get_record_by_idempotency_key",
            "get_chain_records",
            "create_commit_intent",
            "get_commit_intent_by_token",
            "get_commit_intent_by_idempotency_key",
            "get_active_commit_intent_for_chain",
            "update_commit_intent_status",
            "expire_active_commit_intents",
            "get_record_by_id",
        ],
    )

    old_mr = trucon_app_mod._local_mr
    old_quote_adapter = trucon_app_mod._quote_adapter
    old_auth = trucon_app_mod._AUTH_DISABLED
    old_tokens = trucon_app_mod._pending_init_tokens.copy()

    try:
        trucon_app_mod._local_mr = MockMRAdapter()
        trucon_app_mod._quote_adapter = EchoQuoteAdapter(
            quote="mock-owner-quote",
            quote_format="mock-quote-format",
        )
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod.app.state.test_db_path = db_path

        with ExitStack() as stack:
            stack.enter_context(patch.object(trucon_app_mod, "acquire_instance_lock"))
            stack.enter_context(patch.object(trucon_app_mod, "release_instance_lock"))
            stack.enter_context(patch.object(trucon_app_mod, "_crash_recovery"))
            stack.enter_context(patch.object(trucon_app_mod, "_submit_daemon_loop"))
            stack.enter_context(patch.object(trucon_app_mod, "init_db"))
            stack.enter_context(patch.object(trucon_app_mod, "build_baseline_sigstore_bundle", return_value=('{"mock":"bundle"}', 'test-pub-key', 'sha384:' + ('11' * 48))))
            stack.enter_context(patch.object(trucon_app_mod, "SigstoreLogAdapter"))
            stack.enter_context(patch.object(trucon_app_mod, "_extract_bundle_predicate", side_effect=lambda bundle_json: json.loads(bundle_json)))
            stack.enter_context(patch.object(trucon_app_mod, "insert_record", side_effect=patches["insert_record"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_chain_state", side_effect=patches["update_chain_state"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_record_by_idempotency_key", side_effect=patches["get_record_by_idempotency_key"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_chain_records", side_effect=patches["get_chain_records"]))
            stack.enter_context(patch.object(trucon_db_mod, "get_chain_records", side_effect=patches["get_chain_records"]))
            stack.enter_context(patch.object(trucon_app_mod, "create_commit_intent", side_effect=patches["create_commit_intent"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_commit_intent_by_token", side_effect=patches["get_commit_intent_by_token"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_commit_intent_by_idempotency_key", side_effect=patches["get_commit_intent_by_idempotency_key"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_active_commit_intent_for_chain", side_effect=patches["get_active_commit_intent_for_chain"]))
            stack.enter_context(patch.object(trucon_app_mod, "update_commit_intent_status", side_effect=patches["update_commit_intent_status"]))
            stack.enter_context(patch.object(trucon_app_mod, "expire_active_commit_intents", side_effect=patches["expire_active_commit_intents"]))
            stack.enter_context(patch.object(trucon_app_mod, "get_record_by_id", side_effect=patches["get_record_by_id"]))
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client
    finally:
        trucon_app_mod._local_mr = old_mr
        trucon_app_mod._quote_adapter = old_quote_adapter
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._pending_init_tokens.clear()
        trucon_app_mod._pending_init_tokens.update(old_tokens)


def _get_record_payload(record_id: str, db_path: str) -> dict:
    row = trucon_db_mod.get_record_by_id(record_id, db_path=db_path)
    assert row is not None
    return json.loads(row["payload"])


def _make_baseline_bundle(chain_id: str) -> str:
    return json.dumps(
        {
            "chain_id": chain_id,
            "sequence_num": 1,
            "prev_event_digest": None,
            "prev_lookup_hash": None,
            "digest": "sha384:" + ("11" * 48),
        }
    )


def _reserve_baseline_intent(client: TestClient, chain_id: str, idempotency_key: str):
    return client.post(
        "/commit-intents/reserve",
        json={
            "chain_id": chain_id,
            "idempotency_key": idempotency_key,
            "is_baseline": True,
        },
    )


def _generate_owner_keypair():
    private_key = ec.generate_private_key(ec.SECP384R1())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_key


class TestGetBaseline:
    """Tests for GET /init-chain/{chain_id}/baseline."""

    def test_baseline_success(self, trucon_client):
        resp = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp.status_code == 200
        data = resp.json()
        assert data["rtmr_value"] == "aa" * 48
        assert data["init_token"]
        assert len(data["init_token"]) > 0

    def test_baseline_returns_ccel_digest(self, trucon_client):
        with patch.object(trucon_app_mod, "compute_ccel_digest", return_value="sha384:bb" + "cc" * 47):
            resp = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ccel_digest"] == "sha384:bb" + "cc" * 47

    def test_baseline_chain_already_exists_409(self, trucon_client):
        # First, successfully init a chain
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp1.status_code == 200
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        intent_token = reserve.json()["intent_token"]

        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": intent_token,
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        })
        assert resp2.status_code == 200

        # Now GET baseline for same chain should return 409
        resp3 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp3.status_code == 409

    def test_baseline_unique_tokens_before_init(self, trucon_client):
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        resp2 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["init_token"] != resp2.json()["init_token"]


class TestPostInitChain:
    """Tests for POST /init-chain."""

    def test_init_chain_success(self, trucon_client):
        # Phase 1: get baseline
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp1.status_code == 200
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        intent_token = reserve.json()["intent_token"]

        # Phase 2: init chain
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": intent_token,
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----",
        })
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["record_id"]
        assert data["sequence_num"] == 1
        payload = _get_record_payload(data["record_id"], trucon_app_mod.app.state.test_db_path)
        assert payload["pub_key"] == "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----"
        assert payload["owner_attestation"]["chain_id"] == DEFAULT_CHAIN_ID
        assert payload["owner_attestation"]["sequence_num"] == 1
        assert payload["owner_attestation"]["owner_pub_key"] == payload["pub_key"]
        assert payload["owner_attestation"]["report_data_binding"]["bound_fields"] == [
            "chain_id",
            "sequence_num",
            "baseline_rtmr",
            "ccel_digest",
            "owner_pub_key",
        ]

    def test_init_chain_invalid_token_400(self, trucon_client):
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        resp = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": "bogus-token-that-does-not-exist",
            "intent_token": reserve.json()["intent_token"],
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp.status_code == 400
        assert "Invalid or expired" in resp.json()["detail"]

    def test_init_chain_non_default_rejected_400(self, trucon_client):
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200

        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": "chain-b",
            "init_token": token,
            "intent_token": reserve.json()["intent_token"],
            "signed_bundle": _make_baseline_bundle("chain-b"),
            "pub_key": "test-key",
        })
        assert resp2.status_code == 400
        assert "Only the 'default' measured chain is supported" in resp2.json()["detail"]

    def test_init_chain_double_init_409(self, trucon_client):
        # Init chain once
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        token1 = resp1.json()["init_token"]
        reserve1 = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve1.status_code == 200
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token1,
            "intent_token": reserve1.json()["intent_token"],
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200

        # Get another token (should fail at GET since chain exists)
        resp3 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp3.status_code == 409

    def test_init_chain_token_consumed(self, trucon_client):
        """init_token is single-use — replaying it should fail."""
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        intent_token = reserve.json()["intent_token"]

        # First use succeeds
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": intent_token,
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200

        # Second use fails (token consumed)
        resp3 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": intent_token,
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp3.status_code == 400

    def test_commit_after_init_gets_sequence_2(self, trucon_client):
        """After init-chain, the next /commit should get sequence_num=2."""
        # Init chain
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": reserve.json()["intent_token"],
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200
        assert resp2.json()["sequence_num"] == 1

        # Commit should get sequence_num=2
        resp3 = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": DEFAULT_CHAIN_ID,
            "event_digest": "sha384:" + "ab" * 48,
        })
        assert resp3.status_code == 200
        assert resp3.json()["sequence_num"] == 2

    def test_build_commit_after_init_skips_rtmr_extend_and_preserves_mr(self, trucon_client):
        class TrackingMRAdapter(MockMRAdapter):
            def __init__(self):
                self.extend_calls = []

            def extend(self, index: int, digest: str) -> Tuple[str, str]:
                self.extend_calls.append((index, digest))
                return super().extend(index, digest)

        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200
        resp2 = trucon_client.post("/init-chain", json={
            "chain_id": DEFAULT_CHAIN_ID,
            "init_token": token,
            "intent_token": reserve.json()["intent_token"],
            "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
            "pub_key": "test-key",
        })
        assert resp2.status_code == 200

        tracking_mr = TrackingMRAdapter()
        with patch.object(trucon_app_mod, "_local_mr", tracking_mr):
            resp3 = trucon_client.post("/commit", json={
                "bundle": json.dumps({
                    "event_type": "docker_build",
                    "entries": [{"key": "operation_type", "value": "build"}],
                }),
                "chain_id": DEFAULT_CHAIN_ID,
                "event_digest": "sha384:" + "ab" * 48,
            })

        assert resp3.status_code == 200
        assert resp3.json()["sequence_num"] == 2
        assert resp3.json()["mr_value"] == "aa" * 48
        assert resp3.json()["prev_mr_value"] == "aa" * 48
        assert tracking_mr.extend_calls == []

        row = trucon_db_mod.get_record_by_id(resp3.json()["record_id"], db_path=trucon_app_mod.app.state.test_db_path)
        assert row is not None
        assert row["rtmr_extended"] == 1
        assert row["mr_value"] == "aa" * 48

    def test_init_chain_missing_owner_attestation_rejected(self, trucon_client):
        resp1 = trucon_client.get(f"/init-chain/{DEFAULT_CHAIN_ID}/baseline")
        assert resp1.status_code == 200
        token = resp1.json()["init_token"]
        reserve = _reserve_baseline_intent(trucon_client, DEFAULT_CHAIN_ID, f"init-chain-{DEFAULT_CHAIN_ID}")
        assert reserve.status_code == 200

        with patch.object(trucon_app_mod, "_quote_adapter", None):
            resp2 = trucon_client.post("/init-chain", json={
                "chain_id": DEFAULT_CHAIN_ID,
                "init_token": token,
                "intent_token": reserve.json()["intent_token"],
                "signed_bundle": _make_baseline_bundle(DEFAULT_CHAIN_ID),
                "pub_key": "test-key",
            })

        assert resp2.status_code == 500
        assert "Quote adapter is unavailable" in resp2.json()["detail"]


class TestLazyWorkloadBaseline:
    def test_first_default_commit_requires_explicit_baseline(self, trucon_client):
        resp = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": "default",
            "event_digest": "sha384:" + "ab" * 48,
        })

        assert resp.status_code == 409
        assert "create Event Log 0 before committing" in resp.json()["detail"]

        records = trucon_db_mod.get_chain_records("default", db_path=trucon_client.app.state.test_db_path)
        assert records == []

    def test_first_workload_commit_requires_explicit_baseline(self, trucon_client):
        resp = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": "workload-a",
            "event_digest": "sha384:" + "ab" * 48,
        })
        assert resp.status_code == 400

        records = trucon_db_mod.get_chain_records("workload-a", db_path=trucon_client.app.state.test_db_path)
        assert records == []

    def test_concurrent_first_workload_commits_require_explicit_baseline(self, trucon_client):
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

        assert {response.status_code for response in responses} == {400}

        records = trucon_db_mod.get_chain_records("workload-race", db_path=trucon_client.app.state.test_db_path)
        assert records == []

    def test_lazy_baseline_failure_rejects_first_business_event(self, trucon_client):
        resp = trucon_client.post("/commit", json={
            "bundle": '{"payloadType":"test"}',
            "chain_id": "workload-fail",
            "event_digest": "sha384:" + "ab" * 48,
        })

        assert resp.status_code == 400
        records = trucon_db_mod.get_chain_records("workload-fail", db_path=trucon_client.app.state.test_db_path)
        assert records == []

    def test_old_non_default_verify_route_removed(self, trucon_client):
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
            db_path=trucon_client.app.state.test_db_path,
        )

        resp = trucon_client.get("/verify-chain/workload-no-baseline")
        assert resp.status_code == 404

    def test_verify_chain_accepts_pending_baseline_origin(self, trucon_client):
        trucon_db_mod.insert_record(
            record_id="rec-log0",
            event_id="evt-log0-default",
            payload={"bundle": "test", "chain_id": DEFAULT_CHAIN_ID, "is_baseline": True},
            status="PENDING",
            chain_id=DEFAULT_CHAIN_ID,
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=None,
            sequence_num=1,
            event_digest=None,
            db_path=trucon_client.app.state.test_db_path,
        )
        trucon_db_mod.insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test", "chain_id": DEFAULT_CHAIN_ID},
            status="PENDING",
            chain_id=DEFAULT_CHAIN_ID,
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=None,
            sequence_num=2,
            event_digest="sha384:" + "ab" * 48,
            db_path=trucon_client.app.state.test_db_path,
        )

        resp = trucon_client.get("/verify-chain")
        assert resp.status_code == 200
        data = resp.json()
        assert data["entries"][0]["error"] is None
        assert data["rekor_pending"] == 2


class TestCommitIntentLifecycle:
    def _init_chain(self, trucon_client, chain_id: str, pub_key: str = "test-key") -> None:
        chain_id = DEFAULT_CHAIN_ID
        baseline = trucon_client.get(f"/init-chain/{chain_id}/baseline")
        assert baseline.status_code == 200
        reserve = _reserve_baseline_intent(trucon_client, chain_id, f"init-chain-{chain_id}")
        assert reserve.status_code == 200
        resp = trucon_client.post(
            "/init-chain",
            json={
                "chain_id": chain_id,
                "init_token": baseline.json()["init_token"],
                "intent_token": reserve.json()["intent_token"],
                "signed_bundle": _make_baseline_bundle(chain_id),
                "pub_key": pub_key,
            },
        )
        assert resp.status_code == 200

    def test_commit_accepts_matching_owner_authorization(self, trucon_client):
        owner_private_key, owner_pub_key = _generate_owner_keypair()
        self._init_chain(trucon_client, DEFAULT_CHAIN_ID, pub_key=owner_pub_key)
        reserve = trucon_client.post(
            "/commit-intents/reserve",
            json={"chain_id": DEFAULT_CHAIN_ID, "idempotency_key": "commit-owner-ok"},
        )
        assert reserve.status_code == 200
        intent = reserve.json()
        event_digest = "sha384:" + ("ab" * 48)
        owner_authorization = sign_owner_authorization(
            private_key=owner_private_key,
            chain_id=DEFAULT_CHAIN_ID,
            sequence_num=intent["sequence_num"],
            prev_event_digest=intent["prev_event_digest"],
            prev_lookup_hash=intent["prev_lookup_hash"],
            event_digest=event_digest,
        )

        resp = trucon_client.post(
            "/commit",
            json={
                "bundle": json.dumps(
                    {
                        "chain_id": DEFAULT_CHAIN_ID,
                        "sequence_num": intent["sequence_num"],
                        "prev_event_digest": intent["prev_event_digest"],
                        "prev_lookup_hash": intent["prev_lookup_hash"],
                        "digest": event_digest,
                    }
                ),
                "chain_id": DEFAULT_CHAIN_ID,
                "event_digest": event_digest,
                "intent_token": intent["intent_token"],
                "owner_authorization": owner_authorization,
            },
        )

        assert resp.status_code == 200
        payload = _get_record_payload(resp.json()["record_id"], trucon_client.app.state.test_db_path)
        assert payload["owner_authorization"]["algorithm"] == "ecdsa-p384-sha384"

    def test_commit_rejects_missing_owner_authorization(self, trucon_client):
        _owner_private_key, owner_pub_key = _generate_owner_keypair()
        self._init_chain(trucon_client, DEFAULT_CHAIN_ID, pub_key=owner_pub_key)
        reserve = trucon_client.post(
            "/commit-intents/reserve",
            json={"chain_id": DEFAULT_CHAIN_ID, "idempotency_key": "commit-owner-missing"},
        )
        assert reserve.status_code == 200
        intent = reserve.json()
        event_digest = "sha384:" + ("ab" * 48)

        resp = trucon_client.post(
            "/commit",
            json={
                "bundle": json.dumps(
                    {
                        "chain_id": DEFAULT_CHAIN_ID,
                        "sequence_num": intent["sequence_num"],
                        "prev_event_digest": intent["prev_event_digest"],
                        "prev_lookup_hash": intent["prev_lookup_hash"],
                        "digest": event_digest,
                    }
                ),
                "chain_id": DEFAULT_CHAIN_ID,
                "event_digest": event_digest,
                "intent_token": intent["intent_token"],
            },
        )

        assert resp.status_code == 400
        assert "Missing owner authorization" in resp.json()["detail"]

    def test_commit_reuses_consumed_intent_result_with_owner_authorization(self, trucon_client):
        owner_private_key, owner_pub_key = _generate_owner_keypair()
        self._init_chain(trucon_client, DEFAULT_CHAIN_ID, pub_key=owner_pub_key)
        reserve = trucon_client.post(
            "/commit-intents/reserve",
            json={"chain_id": DEFAULT_CHAIN_ID, "idempotency_key": "commit-owner-reuse"},
        )
        assert reserve.status_code == 200
        intent = reserve.json()
        event_digest = "sha384:" + ("ab" * 48)
        owner_authorization = sign_owner_authorization(
            private_key=owner_private_key,
            chain_id=DEFAULT_CHAIN_ID,
            sequence_num=intent["sequence_num"],
            prev_event_digest=intent["prev_event_digest"],
            prev_lookup_hash=intent["prev_lookup_hash"],
            event_digest=event_digest,
        )

        payload = {
            "bundle": json.dumps(
                {
                    "chain_id": DEFAULT_CHAIN_ID,
                    "sequence_num": intent["sequence_num"],
                    "prev_event_digest": intent["prev_event_digest"],
                    "prev_lookup_hash": intent["prev_lookup_hash"],
                    "digest": event_digest,
                }
            ),
            "chain_id": DEFAULT_CHAIN_ID,
            "event_digest": event_digest,
            "intent_token": intent["intent_token"],
            "owner_authorization": owner_authorization,
        }

        first = trucon_client.post("/commit", json=payload)
        second = trucon_client.post("/commit", json=payload)

        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["record_id"] == first.json()["record_id"]

    def test_commit_rejects_bundle_predecessor_mismatch(self, trucon_client):
        self._init_chain(trucon_client, DEFAULT_CHAIN_ID)
        reserve = trucon_client.post(
            "/commit-intents/reserve",
            json={"chain_id": DEFAULT_CHAIN_ID, "idempotency_key": "commit-mismatch"},
        )
        assert reserve.status_code == 200
        intent = reserve.json()

        resp = trucon_client.post(
            "/commit",
            json={
                "bundle": json.dumps(
                    {
                        "chain_id": DEFAULT_CHAIN_ID,
                        "sequence_num": intent["sequence_num"],
                        "prev_event_digest": "sha384:" + ("ff" * 48),
                        "prev_lookup_hash": intent["prev_lookup_hash"],
                        "digest": "sha384:" + ("ab" * 48),
                    }
                ),
                "chain_id": DEFAULT_CHAIN_ID,
                "event_digest": "sha384:" + ("ab" * 48),
                "intent_token": intent["intent_token"],
            },
        )

        assert resp.status_code == 400
        assert "prev_event_digest mismatch" in resp.json()["detail"]

    def test_commit_rejects_expired_intent(self, trucon_client):
        self._init_chain(trucon_client, DEFAULT_CHAIN_ID)
        reserve = trucon_client.post(
            "/commit-intents/reserve",
            json={"chain_id": DEFAULT_CHAIN_ID, "idempotency_key": "expired-intent"},
        )
        assert reserve.status_code == 200
        intent_token = reserve.json()["intent_token"]

        with patch.object(trucon_app_mod, "_intent_expired", return_value=True):
            resp = trucon_client.post(
                "/commit",
                json={
                    "bundle": json.dumps(
                        {
                            "chain_id": DEFAULT_CHAIN_ID,
                            "sequence_num": 2,
                            "prev_event_digest": None,
                            "prev_lookup_hash": None,
                            "digest": "sha384:" + ("ab" * 48),
                        }
                    ),
                    "chain_id": DEFAULT_CHAIN_ID,
                    "event_digest": "sha384:" + ("ab" * 48),
                    "intent_token": intent_token,
                },
            )

        assert resp.status_code == 400
        assert "not active" in resp.json()["detail"]

        stored_intent = trucon_db_mod.get_commit_intent_by_token(
            intent_token,
            db_path=trucon_client.app.state.test_db_path,
        )
        assert stored_intent["status"] == "EXPIRED"

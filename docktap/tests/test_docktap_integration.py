"""
Integration tests for Docktap → TruCon event emission.

4.1: Concurrent Docktap and REST submissions share sequence_num ordering.
4.2: End-to-end Docktap proxy flow with TruCon commit verified in queue.
"""

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

from tc_api.tlog.local_mr import LocalMRAdapter
from tc_api.tlog_client import compute_entry_digest, compute_event_digest
from tc_api.trucon.database import get_chain_state, get_pending_records, init_db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockMRAdapter(LocalMRAdapter):
    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0

    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        with self._lock:
            self._counter += 1
            prev = f"prev-{self._counter - 1:04d}"
            new = f"new-{self._counter:04d}"
            return new, prev


def _make_fake_bundle(event_id: str, event_digest: str) -> str:
    """Create a minimal fake bundle JSON for testing (not cryptographically valid)."""
    return json.dumps({
        "mediaType": "application/vnd.dev.sigstore.bundle+json;version=0.1",
        "verificationMaterial": {},
        "dsseEnvelope": {
            "payload": "",
            "payloadType": "application/vnd.in-toto+json",
            "signatures": [{"sig": "fake", "keyid": ""}],
        },
    })


def _build_commit_payload(event_type: str, entries: list, chain_id: str = "default") -> dict:
    """Build a commit request payload for direct TruCon /commit calls."""
    event_id = f"evt-{uuid.uuid4().hex[:8]}"
    created_iso = datetime.utcnow().isoformat()
    entry_digests = [compute_entry_digest(k, v) for k, v in entries]
    event_digest = compute_event_digest(event_id, event_type, created_iso, entry_digests)
    return {
        "bundle": _make_fake_bundle(event_id, event_digest),
        "chain_id": chain_id,
        "event_digest": event_digest,
        "event_id": event_id,
        "idempotency_key": f"idk-{uuid.uuid4().hex[:12]}",
    }


@pytest.fixture
def trucon_client(tmp_path):
    """Provide a TestClient backed by a fresh TruCon app with mock MR adapter."""
    import importlib
    db_path = str(tmp_path / "queue.db")

    # Set env var BEFORE reloading modules so DB_PATH defaults pick up the test path
    old_env = os.environ.get("COMMIT_QUEUE_DB")
    os.environ["COMMIT_QUEUE_DB"] = db_path

    import tc_api.trucon.database as db_mod
    original_db_path = db_mod.DB_PATH
    # Reload to re-evaluate DB_PATH from env and rebind all function defaults
    importlib.reload(db_mod)
    assert db_mod.DB_PATH == db_path

    # Reload app module so its from-imports pick up the reloaded database functions
    app_mod = importlib.import_module("tc_api.trucon.app")
    importlib.reload(app_mod)

    init_db(db_path)

    old_mr = app_mod._local_mr
    app_mod._local_mr = MockMRAdapter()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient as _TC

    test_app = FastAPI()

    @test_app.post("/commit", response_model=app_mod.CommitResponse)
    def commit(req: app_mod.CommitRequest):
        return app_mod.commit(req)

    @test_app.get("/chain-state/{chain_id}", response_model=app_mod.ChainStateResponse)
    def chain_state(chain_id: str):
        return app_mod.get_chain_state_endpoint(chain_id)

    client = _TC(test_app)
    yield client, db_path

    # Restore
    app_mod._local_mr = old_mr
    if old_env is None:
        os.environ.pop("COMMIT_QUEUE_DB", None)
    else:
        os.environ["COMMIT_QUEUE_DB"] = old_env
    # Reload to restore original DB_PATH
    importlib.reload(db_mod)
    importlib.reload(app_mod)


# ---------------------------------------------------------------------------
# 4.1 — Concurrent Docktap and REST submissions
# ---------------------------------------------------------------------------

class TestConcurrentSubmissions:
    def test_interleaved_sequence_nums(self, trucon_client):
        """Docktap and REST commits on the same chain get monotonic sequence_num."""
        client, db_path = trucon_client

        # Simulate a Docktap "pull" event
        docktap_payload = _build_commit_payload(
            "docker_pull",
            [("operation_type", json.dumps("pull")), ("image_name", json.dumps("nginx"))],
        )
        r1 = client.post("/commit", json=docktap_payload)
        assert r1.status_code == 200
        seq1 = r1.json()["sequence_num"]

        # Simulate a REST "build" event
        rest_payload = _build_commit_payload(
            "build",
            [("build_id", json.dumps("bld-test1"))],
        )
        r2 = client.post("/commit", json=rest_payload)
        assert r2.status_code == 200
        seq2 = r2.json()["sequence_num"]

        # Simulate another Docktap "start" event
        docktap_payload2 = _build_commit_payload(
            "docker_start",
            [("operation_type", json.dumps("start")), ("container_id", json.dumps("abc123"))],
        )
        r3 = client.post("/commit", json=docktap_payload2)
        assert r3.status_code == 200
        seq3 = r3.json()["sequence_num"]

        # Verify monotonically increasing
        assert seq1 < seq2 < seq3
        assert seq1 == 1
        assert seq2 == 2
        assert seq3 == 3

    def test_concurrent_threads_get_distinct_sequence_nums(self, trucon_client):
        """Multiple concurrent submitters get unique, monotonic sequence_num values."""
        client, db_path = trucon_client
        results = []
        errors = []

        def submit(label):
            try:
                payload = _build_commit_payload(
                    f"docker_{label}",
                    [("operation_type", json.dumps(label))],
                )
                r = client.post("/commit", json=payload)
                results.append((label, r.json()["sequence_num"]))
            except Exception as e:
                errors.append((label, str(e)))

        threads = [threading.Thread(target=submit, args=(f"op{i}",)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Submission errors: {errors}"
        assert len(results) == 5

        seq_nums = sorted(s for _, s in results)
        assert seq_nums == [1, 2, 3, 4, 5], f"Expected [1..5], got {seq_nums}"


# ---------------------------------------------------------------------------
# 4.2 — End-to-end Docktap commit flow (mocked signing)
# ---------------------------------------------------------------------------

class TestEndToEndDocktapFlow:
    def test_submit_operation_reaches_trucon_queue(self, trucon_client):
        """TruConCommitter.submit_operation → TruCon /commit → record in queue."""
        client, db_path = trucon_client
        trucon_url = str(client.base_url)  # e.g. http://testserver

        from proxy.operation_log import OperationRecord
        from trucon_client import TruConCommitter

        rec = OperationRecord(
            operation={"type": "pull"},
            image={"name": "alpine", "tag": "3.18", "digest": "sha256:fakeabc"},
        )

        # Mock signing + HTTP to go through TestClient instead of real HTTP
        committer = TruConCommitter(trucon_url=trucon_url)

        with patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken") as mock_id_token, \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = _make_fake_bundle("evt-test", "sha384:fake")
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value._rekor = None
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            # Patch urllib to use TestClient instead
            def fake_urlopen(req, timeout=5):
                body = json.loads(req.data.decode("utf-8"))
                resp = client.post("/commit", json=body)
                mock_resp = MagicMock()
                mock_resp.read.return_value = json.dumps(resp.json()).encode("utf-8")
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = lambda s, *a: None
                return mock_resp

            with patch("trucon_client.urllib.request.urlopen", side_effect=fake_urlopen):
                result = committer.submit_operation(rec, "pull")

        assert result is True

        # Verify record landed in the queue
        state = get_chain_state("default", db_path=db_path)
        assert state is not None
        assert state["sequence_num"] >= 1

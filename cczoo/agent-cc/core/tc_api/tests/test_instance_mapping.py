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
Tests for the workload-instance-mapping change (GAP-03).

Covers:
- 6.1 Schema migration (new DB and existing DB without instance_id column)
- 6.2 Commit with and without instance_id
- 6.3 GET /workloads/{workload_id}/instances (populated, empty, null-instance exclusion)
- 6.4 GET /instances/{instance_id}/events (populated, unknown instance)
- 6.5 GET /workloads/{workload_id}/events (cross-instance, includes null-instance records)
- 6.6 Docktap instance_id submission (container events vs pull)
"""
import sqlite3
import threading
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

from tc_api.trucon.database import (
    get_events_for_instance,
    get_events_for_workload,
    get_instances_for_workload,
    init_db,
    insert_record,
    get_db_connection,
)
from tlog.local_mr import LocalMRAdapter

# Get the actual module object (not the FastAPI app variable)
import importlib
trucon_app_mod = importlib.import_module("tc_api.trucon.app")
import tc_api.trucon.database as trucon_db_mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockMRAdapter(LocalMRAdapter):
    def __init__(self):
        self._lock = threading.Lock()
        self.extends = []

    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        with self._lock:
            prev = "bb" * 48
            new = "cc" * 48
            self.extends.append((index, digest))
            return new, prev


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


def _insert(db, record_id, chain_id="default", instance_id=None, seq=1):
    """Helper to insert a test record."""
    insert_record(
        record_id=record_id,
        event_id=f"evt-{record_id}",
        payload={"bundle": "test"},
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        sequence_num=seq,
        instance_id=instance_id,
        db_path=db,
    )


# ===========================================================================
# 6.1 — Schema migration
# ===========================================================================

class TestSchemaMigration:
    def test_new_db_has_instance_id_column(self, db):
        """Fresh DB should have instance_id column in commit_queue."""
        with get_db_connection(db) as conn:
            cursor = conn.execute("PRAGMA table_info(commit_queue)")
            columns = {row[1] for row in cursor.fetchall()}
        assert "instance_id" in columns

    def test_new_db_has_composite_index(self, db):
        """Fresh DB should have idx_commit_queue_instance index."""
        with get_db_connection(db) as conn:
            cursor = conn.execute("PRAGMA index_list(commit_queue)")
            indexes = {row[1] for row in cursor.fetchall()}
        assert "idx_commit_queue_instance" in indexes

    def test_migration_adds_instance_id_column(self, tmp_path):
        """Existing DB without instance_id column should gain it after init_db."""
        db_path = str(tmp_path / "legacy.db")
        # Create a legacy schema without instance_id
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute('''
                CREATE TABLE commit_queue (
                    record_id TEXT PRIMARY KEY,
                    event_id TEXT,
                    chain_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rtmr_extended BOOLEAN DEFAULT FALSE,
                    log_id TEXT,
                    prev_log_id TEXT,
                    mr_value TEXT,
                    sequence_num INTEGER NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    confirmed_at TEXT,
                    event_digest TEXT,
                    idempotency_key TEXT UNIQUE,
                    created_at TEXT,
                    updated_at TEXT NOT NULL
                )
            ''')
            conn.commit()

        # Run init_db — migration should add instance_id
        init_db(db_path)

        with get_db_connection(db_path) as conn:
            cursor = conn.execute("PRAGMA table_info(commit_queue)")
            columns = {row[1] for row in cursor.fetchall()}
        assert "instance_id" in columns


# ===========================================================================
# 6.2 — Commit with and without instance_id
# ===========================================================================

class TestCommitInstanceId:
    def test_insert_with_instance_id(self, db):
        """Record with instance_id stores and retrieves correctly."""
        _insert(db, "rec-1", instance_id="abc123def456" * 4 + "abc123def456abcd")
        with get_db_connection(db) as conn:
            row = conn.execute("SELECT instance_id FROM commit_queue WHERE record_id='rec-1'").fetchone()
        assert row[0] is not None
        assert len(row[0]) == 64

    def test_insert_without_instance_id(self, db):
        """Record without instance_id stores NULL."""
        _insert(db, "rec-2")
        with get_db_connection(db) as conn:
            row = conn.execute("SELECT instance_id FROM commit_queue WHERE record_id='rec-2'").fetchone()
        assert row[0] is None

    def test_commit_endpoint_with_instance_id(self, db):
        """POST /commit with instance_id stores it in the record."""
        from fastapi.testclient import TestClient

        old_db = trucon_db_mod.DB_PATH
        old_mr = trucon_app_mod._local_mr
        old_auth = trucon_app_mod._AUTH_DISABLED
        try:
            trucon_db_mod.DB_PATH = db
            trucon_app_mod._local_mr = MockMRAdapter()
            trucon_app_mod._AUTH_DISABLED = True
            # Patch DB_PATH default in insert_record at call-time
            orig_insert = trucon_app_mod.insert_record
            def patched_insert(*args, **kwargs):
                kwargs.setdefault("db_path", db)
                return orig_insert(*args, **kwargs)

            with patch.object(trucon_app_mod, "acquire_instance_lock"), \
                 patch.object(trucon_app_mod, "release_instance_lock"), \
                 patch.object(trucon_app_mod, "_crash_recovery"), \
                 patch.object(trucon_app_mod, "init_db"), \
                 patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
                 patch.object(trucon_app_mod, "insert_record", side_effect=patched_insert), \
                 patch.object(trucon_app_mod, "get_chain_state", return_value={"head_log_id": "log0", "sequence_num": 1, "mr_value": "00" * 48}), \
                 patch.object(trucon_app_mod, "update_chain_state"):
                client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
                resp = client.post("/commit", json={
                    "bundle": "test-bundle",
                    "chain_id": "default",
                    "event_digest": "sha384:" + "aa" * 48,
                    "event_id": "evt-test",
                    "instance_id": "c" * 64,
                })
            assert resp.status_code == 200
            data = resp.json()
            record_id = data["record_id"]

            with get_db_connection(db) as conn:
                row = conn.execute("SELECT instance_id FROM commit_queue WHERE record_id=?", (record_id,)).fetchone()
            assert row[0] == "c" * 64
        finally:
            trucon_db_mod.DB_PATH = old_db
            trucon_app_mod._local_mr = old_mr
            trucon_app_mod._AUTH_DISABLED = old_auth

    def test_commit_endpoint_without_instance_id(self, db):
        """POST /commit without instance_id stores NULL."""
        from fastapi.testclient import TestClient

        old_db = trucon_db_mod.DB_PATH
        old_mr = trucon_app_mod._local_mr
        old_auth = trucon_app_mod._AUTH_DISABLED
        try:
            trucon_db_mod.DB_PATH = db
            trucon_app_mod._local_mr = MockMRAdapter()
            trucon_app_mod._AUTH_DISABLED = True
            orig_insert = trucon_app_mod.insert_record
            def patched_insert(*args, **kwargs):
                kwargs.setdefault("db_path", db)
                return orig_insert(*args, **kwargs)

            with patch.object(trucon_app_mod, "acquire_instance_lock"), \
                 patch.object(trucon_app_mod, "release_instance_lock"), \
                 patch.object(trucon_app_mod, "_crash_recovery"), \
                 patch.object(trucon_app_mod, "init_db"), \
                 patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
                 patch.object(trucon_app_mod, "insert_record", side_effect=patched_insert), \
                 patch.object(trucon_app_mod, "get_chain_state", return_value={"head_log_id": "log0", "sequence_num": 1, "mr_value": "00" * 48}), \
                 patch.object(trucon_app_mod, "update_chain_state"):
                client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
                resp = client.post("/commit", json={
                    "bundle": "test-bundle",
                    "chain_id": "default",
                    "event_digest": "sha384:" + "aa" * 48,
                    "event_id": "evt-test2",
                })
            assert resp.status_code == 200
            data = resp.json()
            record_id = data["record_id"]

            with get_db_connection(db) as conn:
                row = conn.execute("SELECT instance_id FROM commit_queue WHERE record_id=?", (record_id,)).fetchone()
            assert row[0] is None
        finally:
            trucon_db_mod.DB_PATH = old_db
            trucon_app_mod._local_mr = old_mr
            trucon_app_mod._AUTH_DISABLED = old_auth


# ===========================================================================
# 6.3 — GET /workloads/{workload_id}/instances
# ===========================================================================

class TestListWorkloadInstances:
    def test_workload_with_multiple_instances(self, db):
        """Returns distinct instances with summary metadata."""
        _insert(db, "rec-1", chain_id="my-app", instance_id="aaa" * 21 + "a", seq=1)
        _insert(db, "rec-2", chain_id="my-app", instance_id="aaa" * 21 + "a", seq=2)
        _insert(db, "rec-3", chain_id="my-app", instance_id="bbb" * 21 + "b", seq=3)

        rows = get_instances_for_workload("my-app", db)
        assert len(rows) == 2
        instance_ids = {r["instance_id"] for r in rows}
        assert "aaa" * 21 + "a" in instance_ids
        assert "bbb" * 21 + "b" in instance_ids
        # First instance has 2 events
        first = [r for r in rows if r["instance_id"] == "aaa" * 21 + "a"][0]
        assert first["event_count"] == 2

    def test_workload_with_no_instances(self, db):
        """Returns empty list for unknown workload."""
        rows = get_instances_for_workload("unknown-app", db)
        assert rows == []

    def test_null_instance_excluded(self, db):
        """Records with instance_id=NULL are excluded."""
        _insert(db, "rec-1", chain_id="my-app", instance_id=None, seq=1)
        _insert(db, "rec-2", chain_id="my-app", instance_id="ccc" * 21 + "c", seq=2)

        rows = get_instances_for_workload("my-app", db)
        assert len(rows) == 1
        assert rows[0]["instance_id"] == "ccc" * 21 + "c"

    def test_endpoint_returns_instances(self, db):
        """GET /workloads/{id}/instances endpoint returns correct response."""
        from fastapi.testclient import TestClient

        old_auth = trucon_app_mod._AUTH_DISABLED
        try:
            trucon_app_mod._AUTH_DISABLED = True
            mock_data = [
                {"instance_id": "d" * 64, "first_event_at": "2026-01-01", "last_event_at": "2026-01-02", "event_count": 3},
                {"instance_id": "e" * 64, "first_event_at": "2026-01-01", "last_event_at": "2026-01-01", "event_count": 1},
            ]

            with patch.object(trucon_app_mod, "acquire_instance_lock"), \
                 patch.object(trucon_app_mod, "release_instance_lock"), \
                 patch.object(trucon_app_mod, "_crash_recovery"), \
                 patch.object(trucon_app_mod, "init_db"), \
                 patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
                 patch.object(trucon_db_mod, "get_instances_for_workload", return_value=mock_data):
                client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
                resp = client.get("/workloads/my-app/instances")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert all("instance_id" in item for item in data)
            assert all("event_count" in item for item in data)
        finally:
            trucon_app_mod._AUTH_DISABLED = old_auth


# ===========================================================================
# 6.4 — GET /instances/{instance_id}/events
# ===========================================================================

class TestListInstanceEvents:
    def test_instance_with_events(self, db):
        """Returns events ordered by sequence_num."""
        _insert(db, "rec-2", chain_id="my-app", instance_id="f" * 64, seq=2)
        _insert(db, "rec-1", chain_id="my-app", instance_id="f" * 64, seq=1)

        rows = get_events_for_instance("f" * 64, db)
        assert len(rows) == 2
        assert rows[0]["sequence_num"] == 1
        assert rows[1]["sequence_num"] == 2

    def test_unknown_instance(self, db):
        """Returns empty list for nonexistent instance."""
        rows = get_events_for_instance("nonexistent", db)
        assert rows == []

    def test_endpoint_returns_events(self, db):
        """GET /instances/{id}/events endpoint returns correct response."""
        from fastapi.testclient import TestClient

        old_auth = trucon_app_mod._AUTH_DISABLED
        try:
            trucon_app_mod._AUTH_DISABLED = True
            mock_data = [
                {"record_id": "r1", "event_id": "e1", "sequence_num": 1, "status": "PENDING", "created_at": "2026-01-01", "instance_id": "g" * 64},
                {"record_id": "r2", "event_id": "e2", "sequence_num": 2, "status": "CONFIRMED", "created_at": "2026-01-02", "instance_id": "g" * 64},
            ]

            with patch.object(trucon_app_mod, "acquire_instance_lock"), \
                 patch.object(trucon_app_mod, "release_instance_lock"), \
                 patch.object(trucon_app_mod, "_crash_recovery"), \
                 patch.object(trucon_app_mod, "init_db"), \
                 patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
                 patch.object(trucon_db_mod, "get_events_for_instance", return_value=mock_data):
                client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
                resp = client.get(f"/instances/{'g' * 64}/events")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
            assert data[0]["sequence_num"] == 1
        finally:
            trucon_app_mod._AUTH_DISABLED = old_auth


# ===========================================================================
# 6.5 — GET /workloads/{workload_id}/events
# ===========================================================================

class TestListWorkloadEvents:
    def test_cross_instance_events(self, db):
        """Returns events from all instances of a workload."""
        _insert(db, "rec-1", chain_id="my-app", instance_id="h" * 64, seq=1)
        _insert(db, "rec-2", chain_id="my-app", instance_id="i" * 64, seq=2)

        rows = get_events_for_workload("my-app", db)
        assert len(rows) == 2
        instance_ids = {r["instance_id"] for r in rows}
        assert len(instance_ids) == 2

    def test_includes_null_instance_records(self, db):
        """Records with instance_id=NULL are included in workload events."""
        _insert(db, "rec-1", chain_id="my-app", instance_id=None, seq=1)
        _insert(db, "rec-2", chain_id="my-app", instance_id="j" * 64, seq=2)

        rows = get_events_for_workload("my-app", db)
        assert len(rows) == 2
        null_records = [r for r in rows if r["instance_id"] is None]
        assert len(null_records) == 1

    def test_endpoint_returns_all_events(self, db):
        """GET /workloads/{id}/events endpoint returns correct response."""
        from fastapi.testclient import TestClient

        old_auth = trucon_app_mod._AUTH_DISABLED
        try:
            trucon_app_mod._AUTH_DISABLED = True
            mock_data = [
                {"record_id": "r1", "event_id": "e1", "sequence_num": 1, "status": "PENDING", "created_at": "2026-01-01", "instance_id": "k" * 64},
                {"record_id": "r2", "event_id": "e2", "sequence_num": 2, "status": "PENDING", "created_at": "2026-01-02", "instance_id": None},
            ]

            with patch.object(trucon_app_mod, "acquire_instance_lock"), \
                 patch.object(trucon_app_mod, "release_instance_lock"), \
                 patch.object(trucon_app_mod, "_crash_recovery"), \
                 patch.object(trucon_app_mod, "init_db"), \
                 patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
                 patch.object(trucon_db_mod, "get_events_for_workload", return_value=mock_data):
                client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
                resp = client.get("/workloads/my-app/events")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data) == 2
        finally:
            trucon_app_mod._AUTH_DISABLED = old_auth


# ===========================================================================
# 6.6 — Docktap instance_id submission
# ===========================================================================

class TestDocktapInstanceId:
    def test_container_event_includes_instance_id(self):
        """Container lifecycle events (create/start/stop/rm) include instance_id."""
        from tc_api.docktap.trucon_client import TruConCommitter
        from tc_api.docktap.proxy.operation_log import OperationRecord

        committer = TruConCommitter(trucon_url="http://localhost:8001")

        for op_type in ["create", "start", "stop", "rm"]:
            rec = OperationRecord(
                operation={"type": op_type},
                image={"name": "myapp"},
                container={"id": "a" * 64, "name": "mycontainer"},
            )
            with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
                 patch.object(committer, "_post_to_trucon") as mock_post, \
                 patch.object(committer, "_ensure_chain_initialized"), \
                 patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 2, "prev_event_digest": None, "prev_lookup_hash": None, "committed": False}), \
                 patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
                 patch("tc_api.docktap.trucon_client.IdentityToken") as mock_id_token, \
                 patch("tc_api.docktap.trucon_client.build_signing_context") as mock_ctx:
                mock_id_token.return_value = MagicMock()
                mock_signer = MagicMock()
                mock_bundle = MagicMock()
                mock_bundle.to_json.return_value = '{"fake": "bundle"}'
                mock_signer.sign_dsse.return_value = mock_bundle
                mock_ctx.return_value._rekor = None
                mock_ctx.return_value.signer.return_value.__enter__ = lambda s: mock_signer
                mock_ctx.return_value.signer.return_value.__exit__ = lambda s, *a: None
                mock_post.return_value = {"record_id": "rec-1", "sequence_num": 1}

                committer._do_submit(rec, op_type)

                call_kwargs = mock_post.call_args
                assert call_kwargs is not None
                assert call_kwargs.kwargs.get("instance_id") == "a" * 64

    def test_pull_event_has_null_instance_id(self):
        """Pull operations have instance_id=None."""
        from tc_api.docktap.trucon_client import TruConCommitter
        from tc_api.docktap.proxy.operation_log import OperationRecord

        committer = TruConCommitter(trucon_url="http://localhost:8001")

        rec = OperationRecord(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest", "digest": "sha256:abc"},
            container={},
        )
        with patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "delegation_disabled"}, clear=False), \
             patch.object(committer, "_post_to_trucon") as mock_post, \
             patch.object(committer, "_ensure_chain_initialized"), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 2, "prev_event_digest": None, "prev_lookup_hash": None, "committed": False}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken") as mock_id_token, \
             patch("tc_api.docktap.trucon_client.build_signing_context") as mock_ctx:
            mock_id_token.return_value = MagicMock()
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.return_value._rekor = None
            mock_ctx.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.return_value.signer.return_value.__exit__ = lambda s, *a: None
            mock_post.return_value = {"record_id": "rec-1", "sequence_num": 1}

            committer._do_submit(rec, "pull")

            call_kwargs = mock_post.call_args
            assert call_kwargs is not None
            assert call_kwargs.kwargs.get("instance_id") is None

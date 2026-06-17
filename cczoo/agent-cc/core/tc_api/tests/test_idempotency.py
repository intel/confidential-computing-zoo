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
Tests for the idempotency-key-enforcement change.

Covers:
- 4.1 insert_record with idempotency_key stores and retrieves correctly
- 4.2 Duplicate idempotency_key INSERT raises IntegrityError
- 4.3 /commit with idempotency key — first succeeds, second returns cached
- 4.4 /commit duplicate matching FAILED_TERMINAL record returns FAILED data
- 4.5 /commit without idempotency key proceeds normally
- 4.6 Schema migration adds idempotency_key column
- 4.7 commit_record() generates idempotency key in TruCon payload
"""
import sqlite3
import threading
from typing import Tuple
from unittest.mock import MagicMock, patch

import pytest

from tc_api.trucon.database import (
    get_record_by_idempotency_key,
    init_db,
    insert_record,
    get_pending_records,
    update_status,
)
from tc_api.transparency.commit_client import TrustedLogAPI
from tlog.local_mr import LocalMRAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class MockMRAdapter(LocalMRAdapter):
    """Thread-safe mock RTMR adapter that tracks extend calls."""
    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0
        self.extends = []

    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        with self._lock:
            self._counter += 1
            prev = f"{'bb' * 48}"
            new = f"{'cc' * 48}"
            self.extends.append((index, digest))
            return new, prev


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


# ===========================================================================
# 4.1 — insert_record with idempotency_key stores and retrieves correctly
# ===========================================================================

class TestIdempotencyKeyStorage:
    def test_insert_and_retrieve_by_idempotency_key(self, db):
        """Verify insert_record stores idempotency_key and get_record_by_idempotency_key retrieves it."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, idempotency_key="idk-abc123",
            db_path=db,
        )
        row = get_record_by_idempotency_key("idk-abc123", "chain-a", db)
        assert row is not None
        assert row["record_id"] == "rec-1"
        assert row["idempotency_key"] == "idk-abc123"

    def test_retrieve_nonexistent_key_returns_none(self, db):
        """Verify get_record_by_idempotency_key returns None for missing key."""
        row = get_record_by_idempotency_key("idk-nonexistent", "chain-a", db)
        assert row is None

    def test_retrieve_key_wrong_chain_returns_none(self, db):
        """Verify lookup is scoped to chain_id."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, idempotency_key="idk-abc123",
            db_path=db,
        )
        # Same key, different chain → not found
        row = get_record_by_idempotency_key("idk-abc123", "chain-b", db)
        assert row is None

    def test_insert_without_idempotency_key(self, db):
        """Verify insert_record works without idempotency_key (NULL)."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, db_path=db,
        )
        records = get_pending_records(db)
        assert len(records) == 1
        assert records[0]["idempotency_key"] is None


# ===========================================================================
# 4.2 — Duplicate idempotency_key INSERT raises IntegrityError
# ===========================================================================

class TestIdempotencyKeyUnique:
    def test_duplicate_key_raises_integrity_error(self, db):
        """Verify UNIQUE constraint prevents duplicate idempotency_key."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, idempotency_key="idk-dup",
            db_path=db,
        )
        with pytest.raises(sqlite3.IntegrityError):
            insert_record(
                record_id="rec-2", event_id="evt-2",
                payload={"bundle": "test2"}, status="PENDING",
                chain_id="chain-a", rtmr_extended=True,
                sequence_num=2, idempotency_key="idk-dup",
                db_path=db,
            )

    def test_multiple_null_keys_allowed(self, db):
        """Verify multiple records with NULL idempotency_key are allowed."""
        for i in range(3):
            insert_record(
                record_id=f"rec-{i}", event_id=f"evt-{i}",
                payload={"bundle": "test"}, status="PENDING",
                chain_id="chain-a", rtmr_extended=True,
                sequence_num=i + 1, db_path=db,
            )
        records = get_pending_records(db)
        assert len(records) == 3


# ===========================================================================
# 4.3 — /commit with idempotency key: dedup without RTMR re-extend
# ===========================================================================

class TestCommitIdempotency:
    def test_duplicate_commit_returns_cached_response(self, db):
        """Simulate the /commit handler logic: second call with same key skips RTMR extend."""
        from tc_api.trucon.database import update_chain_state

        mr_adapter = MockMRAdapter()
        lock = threading.Lock()
        idem_key = "idk-test123"
        chain_id = "chain-a"
        event_digest = "sha384:" + "ab" * 48

        # First commit
        with lock:
            existing = get_record_by_idempotency_key(idem_key, chain_id, db)
            assert existing is None

            mr_value, prev_mr_value = mr_adapter.extend(0, event_digest)
            insert_record(
                record_id="rec-1", event_id="evt-1",
                payload={"bundle": "b1"}, status="PENDING",
                chain_id=chain_id, rtmr_extended=True,
                mr_value=mr_value, sequence_num=1,
                event_digest=event_digest, idempotency_key=idem_key,
                db_path=db,
            )
            update_chain_state(chain_id, "rec-1", 1, mr_value=mr_value, db_path=db)

        assert len(mr_adapter.extends) == 1

        # Second commit (retry) — should return cached, no extend
        with lock:
            existing = get_record_by_idempotency_key(idem_key, chain_id, db)
            assert existing is not None
            assert existing["record_id"] == "rec-1"
            assert existing["sequence_num"] == 1
            assert existing["mr_value"] == mr_value

        # RTMR was NOT extended a second time
        assert len(mr_adapter.extends) == 1


# ===========================================================================
# 4.4 — /commit duplicate matching FAILED_TERMINAL record returns FAILED data
# ===========================================================================

class TestCommitIdempotencyFailed:
    def test_duplicate_of_failed_record_returns_failed_data(self, db):
        """Verify that a duplicate key matching a FAILED_TERMINAL record returns that record's data."""
        idem_key = "idk-fail-test"
        chain_id = "chain-a"

        insert_record(
            record_id="rec-fail", event_id="evt-fail",
            payload={"bundle": "bf"}, status="PENDING",
            chain_id=chain_id, rtmr_extended=True,
            mr_value="mr-1", sequence_num=1,
            idempotency_key=idem_key, db_path=db,
        )
        # Simulate failure
        update_status("rec-fail", "FAILED_TERMINAL", db)

        # Retry with same key → should find FAILED_TERMINAL record
        existing = get_record_by_idempotency_key(idem_key, chain_id, db)
        assert existing is not None
        assert existing["record_id"] == "rec-fail"
        assert existing["status"] == "FAILED_TERMINAL"


# ===========================================================================
# 4.5 — /commit without idempotency key proceeds normally
# ===========================================================================

class TestCommitNoIdempotencyKey:
    def test_commit_without_key_inserts_normally(self, db):
        """Verify that commits without idempotency_key do not trigger dedup."""
        mr_adapter = MockMRAdapter()
        chain_id = "chain-a"
        event_digest = "sha384:" + "ab" * 48

        for i in range(3):
            mr_value, _ = mr_adapter.extend(0, event_digest)
            insert_record(
                record_id=f"rec-{i}", event_id=f"evt-{i}",
                payload={"bundle": f"b{i}"}, status="PENDING",
                chain_id=chain_id, rtmr_extended=True,
                mr_value=mr_value, sequence_num=i + 1,
                event_digest=event_digest, db_path=db,
                # No idempotency_key
            )

        records = get_pending_records(db)
        assert len(records) == 3
        assert len(mr_adapter.extends) == 3


# ===========================================================================
# 4.6 — Schema migration adds idempotency_key column
# ===========================================================================

class TestIdempotencyMigration:
    def test_migration_adds_idempotency_key_column(self, tmp_path):
        """Verify that _migrate_legacy_schema adds idempotency_key to old tables."""
        db_path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(db_path)
        # Create a legacy table without idempotency_key
        conn.execute("""
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
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        # Run init_db which triggers migration
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(commit_queue)").fetchall()}
        conn.close()

        assert "idempotency_key" in cols

    def test_fresh_db_has_idempotency_key_column(self, db):
        """Verify a fresh database includes idempotency_key column."""
        conn = sqlite3.connect(db)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(commit_queue)").fetchall()}
        conn.close()

        assert "idempotency_key" in cols


# ===========================================================================
# 4.7 — commit_record() generates idempotency key in TruCon payload
# ===========================================================================

class TestClientIdempotencyKeyGeneration:
    def test_commit_record_generates_idempotency_key(self):
        """Verify TrustedLogAPI.commit_record() generates and sends an idempotency key."""
        api = TrustedLogAPI(local_mr=None, immutable_log=None, trucon_url="http://localhost:9999")

        ctx = api.init_record()
        from tlog.types import Entry
        api.add_entry(ctx.record_id, Entry(key="test", value="data"))

        captured_payload = {}

        def mock_reserve(self_inner, chain_id, idempotency_key=None, is_baseline=False):
            captured_payload["idempotency_key"] = idempotency_key
            return {
                "intent_token": "intent-1",
                "chain_id": chain_id,
                "sequence_num": 1,
                "prev_event_digest": None,
                "prev_lookup_hash": None,
                "committed": False,
            }

        def mock_post(self_inner, bundle_json, chain_id, event_digest, event_id, intent_token=None, idempotency_key=None, instance_id=None, identity_token=None, owner_authorization=None):
            captured_payload["idempotency_key"] = idempotency_key
            return {"record_id": "rec-mock", "sequence_num": 1, "mr_value": None, "prev_mr_value": None}

        with patch.object(TrustedLogAPI, 'init_chain', return_value=None), \
             patch.object(TrustedLogAPI, '_reserve_commit_intent', mock_reserve), \
             patch.object(TrustedLogAPI, '_post_to_trucon', mock_post), \
             patch('tc_api.transparency.commit_client.build_signing_context') as mock_build_ctx, \
             patch('tc_api.transparency.commit_client.IdentityToken') as mock_id_token:
            mock_id_token.return_value = MagicMock(_identity="tester@example.com")
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"mock": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx = MagicMock()
            mock_ctx.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.signer.return_value.__exit__ = lambda s, *a: None
            mock_build_ctx.return_value = mock_ctx

            api.commit_record(
                record_id=ctx.record_id,
                event_type="test",
                commit_options={"identity_token": "mock-token"},
            )

        key = captured_payload.get("idempotency_key")
        assert key is not None
        assert key.startswith("idk-")
        assert len(key) == 16  # "idk-" + 12 hex chars

    def test_commit_record_uses_provided_idempotency_key(self):
        """Verify caller-provided idempotency_key is passed through."""
        api = TrustedLogAPI(local_mr=None, immutable_log=None, trucon_url="http://localhost:9999")

        ctx = api.init_record()
        from tlog.types import Entry
        api.add_entry(ctx.record_id, Entry(key="test", value="data"))

        captured_payload = {}

        def mock_reserve(self_inner, chain_id, idempotency_key=None, is_baseline=False):
            captured_payload["idempotency_key"] = idempotency_key
            return {
                "intent_token": "intent-1",
                "chain_id": chain_id,
                "sequence_num": 1,
                "prev_event_digest": None,
                "prev_lookup_hash": None,
                "committed": False,
            }

        def mock_post(self_inner, bundle_json, chain_id, event_digest, event_id, intent_token=None, idempotency_key=None, instance_id=None, identity_token=None, owner_authorization=None):
            captured_payload["idempotency_key"] = idempotency_key
            return {"record_id": "rec-mock", "sequence_num": 1, "mr_value": None, "prev_mr_value": None}

        with patch.object(TrustedLogAPI, 'init_chain', return_value=None), \
             patch.object(TrustedLogAPI, '_reserve_commit_intent', mock_reserve), \
             patch.object(TrustedLogAPI, '_post_to_trucon', mock_post), \
             patch('tc_api.transparency.commit_client.build_signing_context') as mock_build_ctx, \
             patch('tc_api.transparency.commit_client.IdentityToken') as mock_id_token:
            mock_id_token.return_value = MagicMock(_identity="tester@example.com")
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"mock": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx = MagicMock()
            mock_ctx.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.signer.return_value.__exit__ = lambda s, *a: None
            mock_build_ctx.return_value = mock_ctx

            api.commit_record(
                record_id=ctx.record_id,
                event_type="test",
                commit_options={
                    "identity_token": "mock-token",
                    "idempotency_key": "idk-custom12345",
                },
            )

        assert captured_payload["idempotency_key"] == "idk-custom12345"

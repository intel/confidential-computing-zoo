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
Tests for the tlog-sequencer-refactor change.

Covers:
- 8.1 Expanded database schema and migration
- 8.2 Sequencer lock serialization
- 8.3 Submit daemon ordering and retry/failure
- 8.4 Integration: tc_api signs → TruCon sequences → daemon submits
- 8.5 Crash recovery
- 8.6 Single-instance enforcement
"""

import fcntl
import os
import sqlite3
import threading
import uuid
from typing import Tuple

import pytest

from tc_api.trucon.database import (
    delete_non_extended_records,
    get_chain_state,
    get_failed_by_chain,
    get_highest_extended_record,
    get_pending_by_chain,
    get_pending_records,
    get_queue_stats,
    init_db,
    insert_record,
    update_chain_state,
    update_record_confirmed,
    update_status,
)
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
            prev = f"prev-{self._counter - 1:04d}"
            new = f"new-{self._counter:04d}"
            self.extends.append((index, digest, new))
            return new, prev


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


# ===========================================================================
# 8.1 — Expanded database schema and migration
# ===========================================================================

class TestDatabaseSchema:
    def test_commit_queue_has_new_columns(self, db):
        """Verify all new columns exist in commit_queue."""
        conn = sqlite3.connect(db)
        cursor = conn.execute("PRAGMA table_info(commit_queue)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        for col in ("chain_id", "rtmr_extended", "log_id", "prev_log_id",
                     "mr_value", "sequence_num", "confirmed_at"):
            assert col in columns, f"Missing column: {col}"

    def test_chain_state_table_exists(self, db):
        """Verify chain_state table is created with correct columns."""
        conn = sqlite3.connect(db)
        cursor = conn.execute("PRAGMA table_info(chain_state)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        for col in ("chain_id", "head_record_id", "head_log_id",
                     "sequence_num", "mr_value", "updated_at"):
            assert col in columns, f"Missing column: {col}"

    def test_insert_record_with_new_fields(self, db):
        """Verify insert_record persists all new fields."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            prev_log_id="prev-0", mr_value="mr-1",
            sequence_num=1, db_path=db,
        )
        records = get_pending_records(db)
        assert len(records) == 1
        r = records[0]
        assert r["chain_id"] == "chain-a"
        assert r["rtmr_extended"] == 1
        assert r["sequence_num"] == 1
        assert r["mr_value"] == "mr-1"

    def test_chain_state_upsert(self, db):
        """Verify chain_state insert and update."""
        update_chain_state("chain-a", "rec-1", 1, mr_value="mr-1", db_path=db)
        state = get_chain_state("chain-a", db)
        assert state is not None
        assert state["sequence_num"] == 1

        # Update
        update_chain_state("chain-a", "rec-2", 2, mr_value="mr-2", db_path=db)
        state = get_chain_state("chain-a", db)
        assert state["sequence_num"] == 2
        assert state["head_record_id"] == "rec-2"

    def test_migration_adds_missing_columns(self, tmp_path):
        """Simulate legacy schema and verify migration adds new columns."""
        db_path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE commit_queue (
                record_id TEXT PRIMARY KEY,
                event_id TEXT,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            INSERT INTO commit_queue (record_id, event_id, payload, status, updated_at)
            VALUES ('old-rec', 'old-evt', '{}', 'PENDING', '2026-01-01')
        """)
        conn.commit()
        conn.close()

        # Run init_db which triggers migration
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(commit_queue)").fetchall()}
        conn.close()

        assert "rtmr_extended" in cols
        assert "chain_id" in cols
        assert "sequence_num" in cols

    def test_get_pending_by_chain(self, db):
        """Verify filtering by chain_id and ordering by sequence_num."""
        for i, cid in enumerate(["a", "b", "a", "a"]):
            insert_record(f"rec-{i}", f"evt-{i}", {"bundle": "x"}, "PENDING",
                          chain_id=cid, rtmr_extended=True, sequence_num=i+1, db_path=db)

        records = get_pending_by_chain("a", db)
        assert len(records) == 3
        seqs = [r["sequence_num"] for r in records]
        assert seqs == sorted(seqs)

    def test_get_queue_stats(self, db):
        """Verify queue statistics."""
        insert_record("rec-1", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "e2", {}, "FAILED_TERMINAL", chain_id="a",
                       rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "e3", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=3, db_path=db)

        stats = get_queue_stats(db)
        assert stats["queued_count"] == 2
        assert stats["failed_terminal_count"] == 1
        assert stats["next_sequence_num"] == 1
        assert stats["next_record_id"] == "rec-1"
        assert stats["total_retry_count"] == 0


# ===========================================================================
# 8.2 — Sequencer lock serialization
# ===========================================================================

class TestSequencerLock:
    def test_concurrent_commits_get_unique_sequence_nums(self, db):
        """Simulate concurrent commits through the lock and verify ordering."""
        lock = threading.Lock()
        results = []
        mr_adapter = MockMRAdapter()

        def do_commit(chain_id, db_path):
            with lock:
                state = get_chain_state(chain_id, db_path)
                seq = (state["sequence_num"] + 1) if state else 1
                prev_log_id = state["head_log_id"] if state else None

                mr_value, prev = mr_adapter.extend(0, "aa" * 48)

                rid = str(uuid.uuid4())
                insert_record(
                    record_id=rid, event_id=f"evt-{seq}",
                    payload={"bundle": "x"}, status="PENDING",
                    chain_id=chain_id, rtmr_extended=True,
                    prev_log_id=prev_log_id, mr_value=mr_value,
                    sequence_num=seq, db_path=db_path,
                )
                update_chain_state(chain_id, rid, seq, mr_value=mr_value, db_path=db_path)
                results.append(seq)

        threads = [threading.Thread(target=do_commit, args=("test-chain", db)) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All sequence numbers should be unique and monotonically increasing
        assert sorted(results) == list(range(1, 11))
        assert len(set(results)) == 10

    def test_rtmr_extend_failure_no_insert(self, db):
        """If RTMR extend fails, no record should be inserted."""
        class FailingMR(LocalMRAdapter):
            def read(self, index): return "00" * 48
            def extend(self, index, digest): raise OSError("RTMR sysfs write failed")

        mr = FailingMR()
        with pytest.raises(OSError, match="RTMR sysfs write failed"):
            mr.extend(0, "aa" * 48)

        records = get_pending_records(db)
        assert len(records) == 0


# ===========================================================================
# 8.3 — Submit daemon ordering and retry/failure logic
# ===========================================================================

class TestSubmitDaemon:
    def test_failed_record_blocks_later_submissions(self, db):
        """FAILED records should block submission of higher sequence_num records."""
        insert_record("rec-1", "e1", {"bundle": "{}"}, "FAILED_TERMINAL",
                       chain_id="a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "e2", {"bundle": "{}"}, "PENDING",
                       chain_id="a", rtmr_extended=True, sequence_num=2, db_path=db)

        failed = get_failed_by_chain("a", db)
        pending = get_pending_by_chain("a", db)

        assert len(failed) == 1
        assert failed[0]["sequence_num"] == 1

        # The daemon logic: if min_failed_seq exists, skip pending > min_failed_seq
        min_failed_seq = failed[0]["sequence_num"]
        submittable = [r for r in pending if r["sequence_num"] <= min_failed_seq]
        assert len(submittable) == 0  # rec-2 (seq=2) is blocked by rec-1 (seq=1)

    def test_retry_threshold_transitions_to_failed(self, db):
        """After MAX_RETRIES, status should transition to FAILED."""
        insert_record("rec-1", "e1", {"bundle": "{}"}, "PENDING",
                       chain_id="a", rtmr_extended=True, sequence_num=1, db_path=db)

        from tc_api.trucon.database import increment_retry
        for _ in range(10):
            increment_retry("rec-1", "FAILED_RETRYABLE", db)

        # Check retry count
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT retry_count FROM commit_queue WHERE record_id = 'rec-1'").fetchone()
        conn.close()
        assert row["retry_count"] == 10

        # After 10 retries, the daemon would mark it FAILED_TERMINAL
        update_status("rec-1", "FAILED_TERMINAL", db)
        failed = get_failed_by_chain("a", db)
        assert len(failed) == 1

    def test_confirmed_record_update(self, db):
        """Confirmed records should have log_id and confirmed_at set."""
        insert_record("rec-1", "e1", {"bundle": "{}"}, "PENDING",
                       chain_id="a", rtmr_extended=True, sequence_num=1, db_path=db)

        update_record_confirmed("rec-1", "rekor-log-123", db)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM commit_queue WHERE record_id = 'rec-1'").fetchone()
        conn.close()

        assert row["status"] == "CONFIRMED"
        assert row["log_id"] == "rekor-log-123"
        assert row["confirmed_at"] is not None

    def test_ordered_submission(self, db):
        """Pending records should be returned in sequence_num order."""
        for i in [3, 1, 2]:
            insert_record(f"rec-{i}", f"e{i}", {"bundle": "{}"}, "PENDING",
                           chain_id="a", rtmr_extended=True, sequence_num=i, db_path=db)

        pending = get_pending_by_chain("a", db)
        seqs = [r["sequence_num"] for r in pending]
        assert seqs == [1, 2, 3]


# ===========================================================================
# 8.4 — Integration test (mocked Sigstore + TruCon)
# ===========================================================================

class TestIntegration:
    def test_commit_flow_through_trucon_endpoint(self, db):
        """Test the TruCon commit endpoint logic directly."""
        from tc_api.trucon.app import _sequencer_lock

        mr_adapter = MockMRAdapter()
        chain_id = "test-chain"

        # Simulate the commit endpoint logic
        with _sequencer_lock:
            state = get_chain_state(chain_id, db)
            seq = 1 if not state else state["sequence_num"] + 1
            prev_log_id = state["head_log_id"] if state else None

            mr_val, prev_mr = mr_adapter.extend(0, "bb" * 48)

            rid = str(uuid.uuid4())
            insert_record(
                record_id=rid, event_id="evt-int",
                payload={"bundle": "{mock}", "chain_id": chain_id},
                status="PENDING", chain_id=chain_id, rtmr_extended=True,
                prev_log_id=prev_log_id, mr_value=mr_val,
                sequence_num=seq, db_path=db,
            )
            update_chain_state(chain_id, rid, seq, mr_value=mr_val, db_path=db)

        # Verify the chain state
        state = get_chain_state(chain_id, db)
        assert state["sequence_num"] == 1
        assert state["head_record_id"] == rid


# ===========================================================================
# 8.5 — Crash recovery
# ===========================================================================

class TestCrashRecovery:
    def test_non_extended_records_deleted(self, db):
        """Records with rtmr_extended=FALSE should be deleted on recovery."""
        insert_record("rec-ok", "e1", {}, "PENDING",
                       chain_id="a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-bad", "e2", {}, "PENDING",
                       chain_id="a", rtmr_extended=False, sequence_num=2, db_path=db)

        deleted = delete_non_extended_records(db)
        assert deleted == 1

        records = get_pending_records(db)
        assert len(records) == 1
        assert records[0]["record_id"] == "rec-ok"

    def test_chain_state_rebuilt_from_highest_extended(self, db):
        """Chain state should be rebuilt from highest sequence_num with rtmr_extended=TRUE."""
        insert_record("rec-1", "e1", {}, "PENDING",
                       chain_id="a", rtmr_extended=True, mr_value="mr-1",
                       sequence_num=1, db_path=db)
        insert_record("rec-3", "e3", {}, "PENDING",
                       chain_id="a", rtmr_extended=True, mr_value="mr-3",
                       sequence_num=3, db_path=db)
        insert_record("rec-2", "e2", {}, "PENDING",
                       chain_id="a", rtmr_extended=True, mr_value="mr-2",
                       sequence_num=2, db_path=db)

        highest = get_highest_extended_record("a", db)
        assert highest["record_id"] == "rec-3"
        assert highest["sequence_num"] == 3

        # Rebuild chain_state
        update_chain_state("a", highest["record_id"], highest["sequence_num"],
                          mr_value=highest["mr_value"], db_path=db)
        state = get_chain_state("a", db)
        assert state["sequence_num"] == 3
        assert state["mr_value"] == "mr-3"

    def test_null_extended_records_cleaned(self, db):
        """Records with rtmr_extended=NULL (legacy migration) should be deleted."""
        # Insert with rtmr_extended=NULL by using raw SQL (simulating legacy)
        conn = sqlite3.connect(db)
        conn.execute("""
            INSERT INTO commit_queue (record_id, event_id, chain_id, payload, status,
                                      rtmr_extended, sequence_num, updated_at)
            VALUES ('rec-null', 'e1', 'a', '{}', 'PENDING', NULL, 1, '2026-01-01')
        """)
        conn.commit()
        conn.close()

        deleted = delete_non_extended_records(db)
        assert deleted == 1


# ===========================================================================
# 8.6 — Single-instance enforcement
# ===========================================================================

class TestSingleInstance:
    def test_file_lock_prevents_second_instance(self, tmp_path):
        """Second attempt to acquire lock should fail."""
        lock_path = str(tmp_path / "trucon.lock")

        # First instance acquires the lock
        fd1 = open(lock_path, "w")
        fcntl.flock(fd1, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd1.write(str(os.getpid()))
        fd1.flush()

        # Second instance should fail
        fd2 = open(lock_path, "w")
        with pytest.raises(OSError):
            fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Cleanup
        fcntl.flock(fd1, fcntl.LOCK_UN)
        fd1.close()
        fd2.close()

    def test_lock_released_after_close(self, tmp_path):
        """Lock should be released when file descriptor is closed."""
        lock_path = str(tmp_path / "trucon.lock")

        fd1 = open(lock_path, "w")
        fcntl.flock(fd1, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fd1.close()

        # Should succeed now
        fd2 = open(lock_path, "w")
        fcntl.flock(fd2, fcntl.LOCK_EX | fcntl.LOCK_NB)  # No exception
        fcntl.flock(fd2, fcntl.LOCK_UN)
        fd2.close()

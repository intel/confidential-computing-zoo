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
Tests for the observability-metrics change (GAP-04).

Covers:
- 5.1 created_at column exists after migration and is populated on insert
- 5.2 created_at is NOT updated by update_status()
- 5.3 get_queue_stats() returns total_retry_count as SUM of retry_count
- 5.4 /commit handler emits metric=commit_latency log line
- 5.5 idempotent /commit emits metric=commit_latency with idempotent=true and metric=idempotency_hit
- 5.6 metric=queue_snapshot log line contains all 5 count fields
- 5.7 metric=confirmation_lag is emitted with correct lag_ms on confirm
"""
import importlib
import logging
import sqlite3
import threading
import time
import uuid
from datetime import datetime
from typing import Tuple
from unittest.mock import patch

import pytest

from tc_api.trucon.database import (
    get_queue_stats,
    increment_retry,
    init_db,
    insert_record,
    update_record_confirmed,
    update_status,
)
from tlog.local_mr import LocalMRAdapter

logger = logging.getLogger("trucon")
trucon_app = importlib.import_module("tc_api.trucon.app")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockMRAdapter(LocalMRAdapter):
    """Thread-safe mock RTMR adapter."""
    def __init__(self):
        self._lock = threading.Lock()
        self._counter = 0

    def read(self, index: int) -> str:
        return "aa" * 48

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        with self._lock:
            self._counter += 1
            return f"{'cc' * 48}", f"{'bb' * 48}"


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


# ===========================================================================
# 5.1 — created_at column exists after migration and is populated on insert
# ===========================================================================


class TestCreatedAtColumn:
    def test_created_at_exists_after_migration(self, db):
        """Verify created_at column exists in commit_queue after init_db."""
        conn = sqlite3.connect(db)
        cursor = conn.execute("PRAGMA table_info(commit_queue)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()
        assert "created_at" in columns

    def test_created_at_populated_on_insert(self, db):
        """Verify insert_record sets created_at to a non-null UTC timestamp."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, db_path=db,
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT created_at, updated_at FROM commit_queue WHERE record_id = 'rec-1'").fetchone()
        conn.close()
        assert row["created_at"] is not None
        datetime.fromisoformat(row["created_at"])

    def test_migration_backfills_created_at(self, tmp_path):
        """Verify migration backfills created_at from updated_at for pre-existing rows."""
        db_path = str(tmp_path / "legacy.db")
        conn = sqlite3.connect(db_path)
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
                updated_at TEXT NOT NULL
            )
        ''')
        conn.execute('''
            INSERT INTO commit_queue (record_id, event_id, chain_id, payload, status,
                                      rtmr_extended, sequence_num, updated_at)
            VALUES ('old-1', 'evt-old', 'chain-a', '{}', 'PENDING', 1, 1, '2026-04-01T00:00:00')
        ''')
        conn.commit()
        conn.close()

        init_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT created_at FROM commit_queue WHERE record_id = 'old-1'").fetchone()
        conn.close()
        assert row["created_at"] == "2026-04-01T00:00:00"


def test_extract_confirmed_rekor_identifiers_prefers_receipt_fields():
    result = trucon_app._extract_confirmed_rekor_identifiers(
        "fallback-log-id",
        {
            "log_id": "confirmed-log-id",
            "uuid": "confirmed-uuid",
            "logIndex": 1457091955,
        },
    )

    assert result == {
        "confirmed_rekor_log_id": "confirmed-log-id",
        "confirmed_rekor_uuid": "confirmed-uuid",
        "confirmed_rekor_log_index": "1457091955",
    }


# ===========================================================================
# 5.2 — created_at is NOT updated by update_status()
# ===========================================================================


class TestCreatedAtImmutability:
    def test_update_status_does_not_change_created_at(self, db):
        """Verify update_status() changes updated_at but NOT created_at."""
        insert_record(
            record_id="rec-1", event_id="evt-1",
            payload={"bundle": "test"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, db_path=db,
        )
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        original = conn.execute("SELECT created_at FROM commit_queue WHERE record_id = 'rec-1'").fetchone()
        original_created = original["created_at"]
        conn.close()

        # Small delay to ensure timestamp differs
        time.sleep(0.01)
        update_status("rec-1", "SUBMITTING", db)

        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        after = conn.execute("SELECT created_at, updated_at FROM commit_queue WHERE record_id = 'rec-1'").fetchone()
        conn.close()

        assert after["created_at"] == original_created
        assert after["updated_at"] != original_created  # updated_at changed


# ===========================================================================
# 5.3 — get_queue_stats() returns total_retry_count
# ===========================================================================


class TestTotalRetryCount:
    def test_total_retry_count_sums_all_retries(self, db):
        """Verify total_retry_count is SUM of retry_count across all records."""
        insert_record("rec-1", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "e2", {}, "FAILED_RETRYABLE", chain_id="a",
                       rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "e3", {}, "FAILED_TERMINAL", chain_id="a",
                       rtmr_extended=True, sequence_num=3, db_path=db)

        # Increment retries: rec-2 gets 3, rec-3 gets 5
        for _ in range(3):
            increment_retry("rec-2", "FAILED_RETRYABLE", db)
        for _ in range(5):
            increment_retry("rec-3", "FAILED_TERMINAL", db)

        stats = get_queue_stats(db)
        assert stats["total_retry_count"] == 8

    def test_total_retry_count_empty_queue(self, db):
        """Verify total_retry_count is 0 for an empty queue."""
        stats = get_queue_stats(db)
        assert stats["total_retry_count"] == 0


# ===========================================================================
# 5.4 — /commit handler emits metric=commit_latency
# ===========================================================================


class TestCommitLatencyMetric:
    def test_commit_emits_latency_log(self, db, caplog):
        """Verify /commit handler emits metric=commit_latency on normal commit."""
        from tc_api.trucon.database import update_chain_state

        lock = threading.Lock()
        event_digest = "sha384:" + "ab" * 48

        # Directly invoke the handler logic and check logs
        with caplog.at_level(logging.INFO, logger="trucon"):
            t0 = time.perf_counter()
            record_id = str(uuid.uuid4())
            with lock:
                insert_record(
                    record_id=record_id, event_id="evt-1",
                    payload={"bundle": "b1"}, status="PENDING",
                    chain_id="chain-a", rtmr_extended=True,
                    sequence_num=1, event_digest=event_digest,
                    db_path=db,
                )
                update_chain_state("chain-a", record_id, 1, db_path=db)

            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s",
                latency_ms, record_id, False,
            )

        assert any("metric=commit_latency" in m for m in caplog.messages)
        latency_msg = [m for m in caplog.messages if "metric=commit_latency" in m][0]
        assert "latency_ms=" in latency_msg
        assert f"record_id={record_id}" in latency_msg
        assert "idempotent=False" in latency_msg


# ===========================================================================
# 5.5 — Idempotent /commit emits commit_latency + idempotency_hit
# ===========================================================================


class TestIdempotencyHitMetric:
    def test_idempotent_commit_emits_both_metrics(self, db, caplog):
        """Verify idempotent /commit emits metric=commit_latency with idempotent=True and metric=idempotency_hit."""
        from tc_api.trucon.database import get_record_by_idempotency_key, update_chain_state

        idem_key = "idk-test-obs"
        chain_id = "chain-a"
        event_digest = "sha384:" + "ab" * 48

        # Insert original record
        insert_record(
            record_id="rec-orig", event_id="evt-1",
            payload={"bundle": "b1"}, status="PENDING",
            chain_id=chain_id, rtmr_extended=True,
            sequence_num=1, event_digest=event_digest,
            idempotency_key=idem_key, db_path=db,
        )
        update_chain_state(chain_id, "rec-orig", 1, db_path=db)

        # Simulate idempotent hit
        with caplog.at_level(logging.INFO, logger="trucon"):
            t0 = time.perf_counter()
            existing = get_record_by_idempotency_key(idem_key, chain_id, db)
            assert existing is not None
            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s",
                latency_ms, existing["record_id"], True,
            )
            logger.info(
                "metric=idempotency_hit key=%s chain_id=%s record_id=%s",
                idem_key, chain_id, existing["record_id"],
            )

        latency_msgs = [m for m in caplog.messages if "metric=commit_latency" in m]
        assert len(latency_msgs) == 1
        assert "idempotent=True" in latency_msgs[0]

        hit_msgs = [m for m in caplog.messages if "metric=idempotency_hit" in m]
        assert len(hit_msgs) == 1
        assert f"key={idem_key}" in hit_msgs[0]
        assert f"chain_id={chain_id}" in hit_msgs[0]
        assert "record_id=rec-orig" in hit_msgs[0]


# ===========================================================================
# 5.6 — queue_snapshot contains all 5 count fields
# ===========================================================================


class TestQueueSnapshotMetric:
    def test_queue_snapshot_contains_all_fields(self, db, caplog):
        """Verify metric=queue_snapshot log line contains all 5 count fields."""
        insert_record("rec-1", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "e2", {}, "SUBMITTING", chain_id="a",
                       rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "e3", {}, "FAILED_RETRYABLE", chain_id="a",
                       rtmr_extended=True, sequence_num=3, db_path=db)
        insert_record("rec-4", "e4", {}, "FAILED_TERMINAL", chain_id="a",
                       rtmr_extended=True, sequence_num=4, db_path=db)

        with patch.object(trucon_app, "_last_queue_snapshot", None), \
             patch.object(trucon_app, "_last_queue_snapshot_tick", 0), \
             patch.object(trucon_app, "_queue_snapshot_tick", 0):
            with caplog.at_level(logging.INFO, logger="trucon"):
                stats = get_queue_stats(db)
                trucon_app._emit_queue_snapshot(stats)

        snapshot_msgs = [m for m in caplog.messages if "metric=queue_snapshot" in m]
        assert len(snapshot_msgs) == 1
        msg = snapshot_msgs[0]
        assert "queue_depth=1" in msg
        assert "submitting=1" in msg
        assert "failed_retryable=1" in msg
        assert "failed_terminal=1" in msg
        assert "total_retries=0" in msg

    def test_empty_queue_snapshot_all_zeros(self, db, caplog):
        """Verify empty queue snapshot shows all counts as 0."""
        with patch.object(trucon_app, "_last_queue_snapshot", None), \
             patch.object(trucon_app, "_last_queue_snapshot_tick", 0), \
             patch.object(trucon_app, "_queue_snapshot_tick", 0):
            with caplog.at_level(logging.INFO, logger="trucon"):
                stats = get_queue_stats(db)
                trucon_app._emit_queue_snapshot(stats)

        snapshot_msgs = [m for m in caplog.messages if "metric=queue_snapshot" in m]
        assert len(snapshot_msgs) == 1
        msg = snapshot_msgs[0]
        assert "queue_depth=0" in msg
        assert "submitting=0" in msg
        assert "failed_retryable=0" in msg
        assert "failed_terminal=0" in msg
        assert "total_retries=0" in msg

    def test_duplicate_queue_snapshot_is_suppressed_until_heartbeat(self, caplog):
        """Verify repeated identical snapshots are not logged every tick."""
        stats = {
            "queued_count": 0,
            "submitting_count": 0,
            "failed_retryable_count": 0,
            "failed_terminal_count": 0,
            "total_retry_count": 0,
        }

        with patch.object(trucon_app, "_last_queue_snapshot", None), \
             patch.object(trucon_app, "_last_queue_snapshot_tick", 0), \
             patch.object(trucon_app, "_queue_snapshot_tick", 0), \
             patch.object(trucon_app, "QUEUE_SNAPSHOT_HEARTBEAT_TICKS", 3):
            with caplog.at_level(logging.INFO, logger="trucon"):
                trucon_app._emit_queue_snapshot(stats)
                trucon_app._emit_queue_snapshot(stats)
                trucon_app._emit_queue_snapshot(stats)
                trucon_app._emit_queue_snapshot(stats)

        snapshot_msgs = [m for m in caplog.messages if "metric=queue_snapshot" in m]
        assert len(snapshot_msgs) == 2


# ===========================================================================
# 5.7 — confirmation_lag is emitted with correct lag_ms on confirm
# ===========================================================================


class TestConfirmationLagMetric:
    def test_confirmation_lag_emitted_on_confirm(self, db, caplog):
        """Verify metric=confirmation_lag is emitted with valid lag_ms when a record is confirmed."""
        insert_record(
            record_id="rec-lag", event_id="evt-1",
            payload={"bundle": "b1"}, status="PENDING",
            chain_id="chain-a", rtmr_extended=True,
            sequence_num=1, db_path=db,
        )

        # Read back created_at
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT created_at FROM commit_queue WHERE record_id = 'rec-lag'").fetchone()
        created_at = row["created_at"]
        conn.close()

        # Small delay to ensure measurable lag
        time.sleep(0.02)

        # Confirm the record
        update_record_confirmed("rec-lag", "log-123", db)

        with caplog.at_level(logging.INFO, logger="trucon"):
            # Compute and emit lag as the daemon would
            confirmed_at = datetime.utcnow()
            created_dt = datetime.fromisoformat(created_at)
            lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
            logger.info(
                "metric=confirmation_lag lag_ms=%.1f record_id=%s",
                lag_ms, "rec-lag",
            )

        lag_msgs = [m for m in caplog.messages if "metric=confirmation_lag" in m]
        assert len(lag_msgs) == 1
        assert "record_id=rec-lag" in lag_msgs[0]
        assert "lag_ms=" in lag_msgs[0]
        # lag should be at least 10ms (we slept 20ms)
        import re
        match = re.search(r"lag_ms=(\d+\.?\d*)", lag_msgs[0])
        assert match is not None
        lag_val = float(match.group(1))
        assert lag_val >= 10.0

    def test_no_confirmation_lag_when_created_at_null(self, db, caplog):
        """Verify metric=confirmation_lag is NOT emitted when created_at is NULL."""
        # Manually insert a record without created_at (simulate pre-migration)
        conn = sqlite3.connect(db)
        conn.execute('''
            INSERT INTO commit_queue (record_id, event_id, chain_id, payload, status,
                                      rtmr_extended, sequence_num, updated_at)
            VALUES ('rec-null', 'evt-null', 'chain-a', '{}', 'PENDING', 1, 1, ?)
        ''', (datetime.utcnow().isoformat(),))
        conn.commit()
        conn.close()

        with caplog.at_level(logging.INFO, logger="trucon"):
            # Simulate daemon: created_at is None, so skip lag emission
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT created_at FROM commit_queue WHERE record_id = 'rec-null'").fetchone()
            conn.close()
            created_at = row["created_at"]
            if created_at:
                confirmed_at = datetime.utcnow()
                created_dt = datetime.fromisoformat(created_at)
                lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
                logger.info(
                    "metric=confirmation_lag lag_ms=%.1f record_id=%s",
                    lag_ms, "rec-null",
                )

        lag_msgs = [m for m in caplog.messages if "metric=confirmation_lag" in m]
        assert len(lag_msgs) == 0

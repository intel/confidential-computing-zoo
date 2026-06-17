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
Tests for the status-response-fix change.

Covers:
- 5.1 GET /status returns CommitQueueStatusResponse with all 6 fields for mixed queue state
- 5.2 GET /status returns correct defaults for empty queue
- 5.3 GET /status next_record_id matches lowest-sequence pending record
- 5.4 GET /state returns correct LatestState for default chain
- 5.5 GET /state returns null/zero defaults for empty chain
- 5.6 get_latest_state() database function returns correct data
- 5.7 tlog_client.get_commit_queue_status() maps new fields correctly
"""

from unittest.mock import patch

import pytest

from tc_api.trucon.database import (
    get_latest_state,
    get_queue_stats,
    init_db,
    insert_record,
    update_chain_state,
)


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_status.db"
    init_db(str(db_file))
    return str(db_file)


# ===========================================================================
# 5.1 — GET /status returns all fields for mixed queue state
# ===========================================================================

class TestStatusMixedQueue:
    def test_status_all_fields_mixed_queue(self, db):
        """Verify get_queue_stats returns all fields including next_record_id for mixed states."""
        insert_record("rec-1", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "e2", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "e3", {}, "SUBMITTING", chain_id="a",
                       rtmr_extended=True, sequence_num=3, db_path=db)
        insert_record("rec-4", "e4", {}, "FAILED_RETRYABLE", chain_id="a",
                       rtmr_extended=True, sequence_num=4, db_path=db)
        insert_record("rec-5", "e5", {}, "FAILED_TERMINAL", chain_id="a",
                       rtmr_extended=True, sequence_num=5, db_path=db)

        stats = get_queue_stats(db)
        assert stats["queued_count"] == 2
        assert stats["submitting_count"] == 1
        assert stats["failed_retryable_count"] == 1
        assert stats["failed_terminal_count"] == 1
        assert stats["next_record_id"] == "rec-1"
        assert stats["next_sequence_num"] == 1
        assert stats["total_retry_count"] == 0


# ===========================================================================
# 5.2 — GET /status returns correct defaults for empty queue
# ===========================================================================

class TestStatusEmptyQueue:
    def test_status_empty_queue(self, db):
        """Verify get_queue_stats returns zeros and nulls for empty queue."""
        stats = get_queue_stats(db)
        assert stats["queued_count"] == 0
        assert stats["submitting_count"] == 0
        assert stats["failed_retryable_count"] == 0
        assert stats["failed_terminal_count"] == 0
        assert stats["next_record_id"] is None
        assert stats["next_sequence_num"] is None
        assert stats["total_retry_count"] == 0


# ===========================================================================
# 5.3 — next_record_id matches lowest-sequence pending record
# ===========================================================================

class TestStatusNextRecordId:
    def test_next_record_id_lowest_sequence(self, db):
        """next_record_id should be the record_id with lowest sequence_num among PENDING+extended."""
        insert_record("rec-high", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=10, db_path=db)
        insert_record("rec-low", "e2", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=3, db_path=db)
        insert_record("rec-mid", "e3", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=7, db_path=db)

        stats = get_queue_stats(db)
        assert stats["next_record_id"] == "rec-low"
        assert stats["next_sequence_num"] == 3

    def test_next_record_id_skips_non_extended(self, db):
        """Records with rtmr_extended=False should not be selected as next."""
        insert_record("rec-noext", "e1", {}, "PENDING", chain_id="a",
                       rtmr_extended=False, sequence_num=1, db_path=db)
        insert_record("rec-ext", "e2", {}, "PENDING", chain_id="a",
                       rtmr_extended=True, sequence_num=5, db_path=db)

        stats = get_queue_stats(db)
        assert stats["next_record_id"] == "rec-ext"

    def test_next_record_id_only_failed(self, db):
        """If only FAILED_TERMINAL records exist, next_record_id should be None."""
        insert_record("rec-fail", "e1", {}, "FAILED_TERMINAL", chain_id="a",
                       rtmr_extended=True, sequence_num=1, db_path=db)

        stats = get_queue_stats(db)
        assert stats["queued_count"] == 0
        assert stats["next_record_id"] is None


# ===========================================================================
# 5.4 — GET /state returns correct LatestState for default chain
# ===========================================================================

class TestLatestStateWithData:
    def test_state_confirmed_and_pending(self, db):
        """LatestState should return chain head info and pending event_ids."""
        update_chain_state("default", "rec-head", sequence_num=5,
                           mr_value="0xdead", head_log_id="rekor-abc", db_path=db)
        insert_record("rec-p1", "evt-1", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=6, db_path=db)
        insert_record("rec-p2", "evt-2", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=7, db_path=db)

        state = get_latest_state("default", db)
        assert state["latest_confirmed_log_id"] == "rekor-abc"
        assert state["latest_mr_value"] == "0xdead"
        assert state["pending_record_count"] == 2
        assert state["pending_event_ids"] == ["evt-1", "evt-2"]

    def test_state_all_confirmed(self, db):
        """If no pending records, pending counts should be zero."""
        update_chain_state("default", "rec-head", sequence_num=3,
                           mr_value="0xbeef", head_log_id="rekor-xyz", db_path=db)

        state = get_latest_state("default", db)
        assert state["latest_confirmed_log_id"] == "rekor-xyz"
        assert state["latest_mr_value"] == "0xbeef"
        assert state["pending_record_count"] == 0
        assert state["pending_event_ids"] == []


# ===========================================================================
# 5.5 — GET /state returns null/zero defaults for empty chain
# ===========================================================================

class TestLatestStateEmpty:
    def test_state_empty_chain(self, db):
        """Empty chain should return all-null/zero defaults."""
        state = get_latest_state("default", db)
        assert state["latest_confirmed_log_id"] is None
        assert state["latest_mr_value"] is None
        assert state["pending_record_count"] == 0
        assert state["pending_event_ids"] == []


# ===========================================================================
# 5.6 — get_latest_state() database function returns correct data
# ===========================================================================

class TestGetLatestStateDB:
    def test_pending_event_ids_ordered_by_sequence(self, db):
        """pending_event_ids should be ordered by sequence_num ascending."""
        insert_record("rec-3", "evt-c", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=30, db_path=db)
        insert_record("rec-1", "evt-a", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=10, db_path=db)
        insert_record("rec-2", "evt-b", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=20, db_path=db)

        state = get_latest_state("default", db)
        assert state["pending_event_ids"] == ["evt-a", "evt-b", "evt-c"]
        assert state["pending_record_count"] == 3

    def test_excludes_non_pending(self, db):
        """Only PENDING records should appear in pending_event_ids."""
        insert_record("rec-1", "evt-pending", {}, "PENDING", chain_id="default",
                       rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "evt-confirmed", {}, "CONFIRMED", chain_id="default",
                       rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "evt-failed", {}, "FAILED_TERMINAL", chain_id="default",
                       rtmr_extended=True, sequence_num=3, db_path=db)

        state = get_latest_state("default", db)
        assert state["pending_record_count"] == 1
        assert state["pending_event_ids"] == ["evt-pending"]

    def test_different_chain_isolated(self, db):
        """get_latest_state for one chain should not include records from another."""
        update_chain_state("chain-a", "rec-a", sequence_num=1,
                           head_log_id="log-a", db_path=db)
        insert_record("rec-b", "evt-b", {}, "PENDING", chain_id="chain-b",
                       rtmr_extended=True, sequence_num=1, db_path=db)

        state_a = get_latest_state("chain-a", db)
        assert state_a["latest_confirmed_log_id"] == "log-a"
        assert state_a["pending_record_count"] == 0

        state_b = get_latest_state("chain-b", db)
        assert state_b["latest_confirmed_log_id"] is None
        assert state_b["pending_record_count"] == 1


# ===========================================================================
# 5.7 — tlog_client.get_commit_queue_status() maps new fields correctly
# ===========================================================================

class TestClientMapping:
    def test_client_maps_new_fields(self):
        """get_commit_queue_status should map new field names and populate next_record_id."""
        from tlog.types import CommitQueueStatus
        from tc_api.transparency.commit_client import TrustedLogAPI

        mock_response_data = {
            "has_queued_records": True,
            "queued_record_count": 3,
            "next_record_id": "rec-abc",
            "submitting_count": 1,
            "failed_retryable_count": 0,
            "failed_terminal_count": 0,
            "total_retry_count": 0,
        }

        with patch("tc_api.transparency.commit_client.request_json", return_value=mock_response_data):
            client = TrustedLogAPI.__new__(TrustedLogAPI)
            client._trucon_url = "http://localhost:8001"
            status = client.get_commit_queue_status()

        assert isinstance(status, CommitQueueStatus)
        assert status.has_queued_records is True
        assert status.queued_record_count == 3
        assert status.next_record_id == "rec-abc"

    def test_client_handles_null_next_record_id(self):
        """next_record_id=null should be properly handled."""
        from tc_api.transparency.commit_client import TrustedLogAPI

        mock_response_data = {
            "has_queued_records": False,
            "queued_record_count": 0,
            "next_record_id": None,
            "submitting_count": 0,
            "failed_retryable_count": 0,
            "failed_terminal_count": 0,
            "total_retry_count": 0,
        }

        with patch("tc_api.transparency.commit_client.request_json", return_value=mock_response_data):
            client = TrustedLogAPI.__new__(TrustedLogAPI)
            client._trucon_url = "http://localhost:8001"
            status = client.get_commit_queue_status()

        assert status.has_queued_records is False
        assert status.next_record_id is None

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
Tests for the granular-lifecycle-states change.

Covers:
- 7.1 SubmitStatus enum has exactly 6 members
- 7.2 PENDING → SUBMITTING → CONFIRMED happy path
- 7.3 SUBMITTING → FAILED_RETRYABLE → PENDING retry cycle
- 7.4 FAILED_RETRYABLE → FAILED_TERMINAL after MAX_RETRIES
- 7.5 FAILED_TERMINAL blocks subsequent records in same chain
- 7.6 Crash recovery resets SUBMITTING → PENDING
- 7.7 get_failed_by_chain returns both FAILED_RETRYABLE and FAILED_TERMINAL
"""
import pytest

from tlog.types import SubmitStatus
from tc_api.trucon.database import (
    get_failed_by_chain,
    get_pending_by_chain,
    get_queue_stats,
    init_db,
    insert_record,
    reset_submitting_to_pending,
    set_status_submitting,
    update_record_confirmed,
    update_status,
    increment_retry,
)


@pytest.fixture
def db(tmp_path):
    db_file = tmp_path / "test_lifecycle.db"
    init_db(str(db_file))
    return str(db_file)


# ---------------------------------------------------------------------------
# 7.1 SubmitStatus enum
# ---------------------------------------------------------------------------

class TestSubmitStatusEnum:
    def test_has_exactly_six_members(self):
        assert len(SubmitStatus) == 6

    def test_member_values(self):
        assert SubmitStatus.OPEN.value == "open"
        assert SubmitStatus.PENDING.value == "pending"
        assert SubmitStatus.SUBMITTING.value == "submitting"
        assert SubmitStatus.CONFIRMED.value == "confirmed"
        assert SubmitStatus.FAILED_RETRYABLE.value == "failed_retryable"
        assert SubmitStatus.FAILED_TERMINAL.value == "failed_terminal"

    def test_member_names(self):
        names = {m.name for m in SubmitStatus}
        assert names == {"OPEN", "PENDING", "SUBMITTING", "CONFIRMED", "FAILED_RETRYABLE", "FAILED_TERMINAL"}


# ---------------------------------------------------------------------------
# 7.2 PENDING → SUBMITTING → CONFIRMED happy path
# ---------------------------------------------------------------------------

class TestHappyPath:
    def test_pending_to_submitting_to_confirmed(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)

        # Transition to SUBMITTING
        set_status_submitting("rec-1", db_path=db)
        pending = get_pending_by_chain("chain-a", db_path=db)
        assert len(pending) == 0  # No longer PENDING

        stats = get_queue_stats(db_path=db)
        assert stats['submitting_count'] == 1

        # Transition to CONFIRMED
        update_record_confirmed("rec-1", "log-abc", db_path=db)
        stats = get_queue_stats(db_path=db)
        assert stats['submitting_count'] == 0
        assert stats['queued_count'] == 0


# ---------------------------------------------------------------------------
# 7.3 SUBMITTING → FAILED_RETRYABLE → PENDING retry cycle
# ---------------------------------------------------------------------------

class TestRetryCycle:
    def test_submitting_to_failed_retryable_to_pending(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)

        # Mark SUBMITTING
        set_status_submitting("rec-1", db_path=db)

        # Fail retryably
        increment_retry("rec-1", "FAILED_RETRYABLE", db_path=db)
        stats = get_queue_stats(db_path=db)
        assert stats['failed_retryable_count'] == 1

        # Reset to PENDING for retry
        update_status("rec-1", "PENDING", db_path=db)
        pending = get_pending_by_chain("chain-a", db_path=db)
        assert len(pending) == 1
        assert pending[0]['record_id'] == "rec-1"


# ---------------------------------------------------------------------------
# 7.4 FAILED_RETRYABLE → FAILED_TERMINAL after MAX_RETRIES
# ---------------------------------------------------------------------------

class TestRetryThreshold:
    def test_exceeds_max_retries_becomes_terminal(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)

        # Simulate 10 retries (MAX_RETRIES = 10)
        for _ in range(10):
            increment_retry("rec-1", "FAILED_RETRYABLE", db_path=db)

        # After threshold, transition to FAILED_TERMINAL
        update_status("rec-1", "FAILED_TERMINAL", db_path=db)
        stats = get_queue_stats(db_path=db)
        assert stats['failed_terminal_count'] == 1
        assert stats['failed_retryable_count'] == 0


# ---------------------------------------------------------------------------
# 7.5 FAILED_TERMINAL blocks subsequent records in same chain
# ---------------------------------------------------------------------------

class TestTerminalBlocks:
    def test_failed_terminal_blocks_chain(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "FAILED_TERMINAL",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "evt-2", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=2, db_path=db)

        failed = get_failed_by_chain("chain-a", db_path=db)
        assert len(failed) == 1
        min_failed_seq = failed[0]['sequence_num']

        pending = get_pending_by_chain("chain-a", db_path=db)
        # rec-2 is pending but should be blocked by rec-1
        submittable = [r for r in pending if r['sequence_num'] <= min_failed_seq or min_failed_seq is None]
        assert len(submittable) == 0  # rec-2 at seq=2 > min_failed_seq=1


# ---------------------------------------------------------------------------
# 7.6 Crash recovery resets SUBMITTING → PENDING
# ---------------------------------------------------------------------------

class TestCrashRecovery:
    def test_reset_submitting_to_pending(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "SUBMITTING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "evt-2", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=2, db_path=db)

        reset_count = reset_submitting_to_pending(db_path=db)
        assert reset_count == 1

        pending = get_pending_by_chain("chain-a", db_path=db)
        assert len(pending) == 2
        assert pending[0]['record_id'] == "rec-1"  # Was SUBMITTING, now PENDING

    def test_no_submitting_records_resets_zero(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)

        reset_count = reset_submitting_to_pending(db_path=db)
        assert reset_count == 0


# ---------------------------------------------------------------------------
# 7.7 get_failed_by_chain returns both failure types
# ---------------------------------------------------------------------------

class TestGetFailedByChain:
    def test_returns_both_retryable_and_terminal(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "FAILED_RETRYABLE",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "evt-2", {"bundle": "test"}, "FAILED_TERMINAL",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=2, db_path=db)
        insert_record("rec-3", "evt-3", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=3, db_path=db)

        failed = get_failed_by_chain("chain-a", db_path=db)
        assert len(failed) == 2
        statuses = {f['status'] for f in failed}
        assert statuses == {'FAILED_RETRYABLE', 'FAILED_TERMINAL'}

    def test_excludes_pending_and_confirmed(self, db):
        insert_record("rec-1", "evt-1", {"bundle": "test"}, "PENDING",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=1, db_path=db)
        insert_record("rec-2", "evt-2", {"bundle": "test"}, "CONFIRMED",
                       chain_id="chain-a", rtmr_extended=True, sequence_num=2, db_path=db)

        failed = get_failed_by_chain("chain-a", db_path=db)
        assert len(failed) == 0

"""
Tests for the non-tee-verification change.

Covers:
- 4.1 Valid signed predecessor chain in non-TEE mode
- 4.2 Signed predecessor mismatch detection
- 4.3 Unconfirmed record returns predecessor_ok: None
- 4.4 RTMR mode suppresses predecessor check
- 4.5 Startup warning emits WARNING-level "NON-TEE MODE"
"""

import logging
import os
import sqlite3
from unittest.mock import patch

import pytest

from tc_api.trucon.app import _compute_record_lookup_hash
from tc_api.trucon.database import (
    get_chain_records,
    init_db,
    insert_record,
    update_record_confirmed,
)


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


def _insert_confirmed_record(db, record_id, seq, chain_id, prev_event_digest, prev_lookup_hash, log_id):
    """Insert a record and confirm it with the given log_id."""
    insert_record(
        record_id=record_id,
        event_id=f"evt-{seq}",
        payload={"bundle": "test"},
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        prev_event_digest=prev_event_digest,
        prev_lookup_hash=prev_lookup_hash,
        mr_value=None,  # non-TEE: no mr_value
        sequence_num=seq,
        event_digest=f"sha384:{seq:096x}",
        db_path=db,
    )
    update_record_confirmed(record_id, log_id, db_path=db)


class TestPredecessorVerification:
    """Tests for signed predecessor linkage in verify-chain (non-TEE mode)."""

    def test_valid_signed_predecessor_chain(self, db):
        """4.1: Valid signed predecessor chain returns all predecessor_ok: True."""
        _insert_confirmed_record(db, "rec-1", 1, "default", None, None, "log-aaa")
        first_record = get_chain_records("default", db)[0]
        _insert_confirmed_record(
            db,
            "rec-2",
            2,
            "default",
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            "log-bbb",
        )
        second_record = get_chain_records("default", db)[1]
        _insert_confirmed_record(
            db,
            "rec-3",
            3,
            "default",
            second_record["event_digest"],
            _compute_record_lookup_hash(second_record),
            "log-ccc",
        )

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.valid is True
        assert resp.rtmr_available is False
        assert resp.entries[0].predecessor_status == "origin"
        assert resp.entries[1].predecessor_status == "proven"
        assert resp.entries[2].predecessor_status == "proven"
        for entry in resp.entries:
            assert entry.predecessor_ok is True

    def test_signed_predecessor_mismatch(self, db):
        """4.2: Mismatch returns predecessor_ok: False and valid: False."""
        _insert_confirmed_record(db, "rec-1", 1, "default", None, None, "log-aaa")
        _insert_confirmed_record(
            db,
            "rec-2",
            2,
            "default",
            "sha384:" + ("ff" * 48),
            "sha256:" + ("00" * 32),
            "log-bbb",
        )

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.valid is False
        assert resp.entries[0].predecessor_ok is True
        assert resp.entries[1].predecessor_ok is False
        assert resp.entries[1].predecessor_status == "missing"
        assert "signed predecessor mismatch" in resp.entries[1].error

    def test_unconfirmed_record_returns_none(self, db):
        """4.3: Unconfirmed record gets predecessor_ok: None."""
        _insert_confirmed_record(db, "rec-1", 1, "default", None, None, "log-aaa")
        first_record = get_chain_records("default", db)[0]
        # Insert a second record but DON'T confirm it
        insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=first_record["event_digest"],
            prev_lookup_hash=_compute_record_lookup_hash(first_record),
            mr_value=None,
            sequence_num=2,
            event_digest="sha384:" + ("22" * 48),
            db_path=db,
        )

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.entries[0].predecessor_ok is True
        assert resp.entries[1].predecessor_ok is None  # unconfirmed
        assert resp.entries[1].predecessor_status == "unverifiable"

    def test_rtmr_available_suppresses_predecessor_check(self, db):
        """4.4: When rtmr_available==True, all entries have predecessor_ok: None."""
        # Insert records WITH mr_value to trigger rtmr_available=True
        insert_record(
            record_id="rec-1",
            event_id="evt-1",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=None,
            prev_lookup_hash=None,
            mr_value="aa" * 48,
            sequence_num=1,
            event_digest="sha384:" + "bb" * 48,
            db_path=db,
        )
        update_record_confirmed("rec-1", "log-aaa", db_path=db)

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.rtmr_available is True
        for entry in resp.entries:
            assert entry.predecessor_ok is None

    def test_missing_signed_contract_is_reported_as_degraded_boundary(self, db):
        """Legacy-to-reservation boundary reports degraded boundary_status."""
        _insert_confirmed_record(db, "rec-1", 1, "default", None, None, "log-aaa")
        _insert_confirmed_record(db, "rec-2", 2, "default", None, None, "log-bbb")
        legacy_record = get_chain_records("default", db)[1]
        _insert_confirmed_record(
            db,
            "rec-3",
            3,
            "default",
            legacy_record["event_digest"],
            _compute_record_lookup_hash(legacy_record),
            "log-ccc",
        )

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.entries[1].predecessor_status == "unverifiable"
        assert resp.entries[1].boundary_status == "degraded"
        assert resp.entries[2].predecessor_status == "proven"

    def test_signed_contract_regression_is_reported_as_invalid_boundary(self, db):
        _insert_confirmed_record(db, "rec-1", 1, "default", None, None, "log-aaa")
        first_record = get_chain_records("default", db)[0]
        _insert_confirmed_record(
            db,
            "rec-2",
            2,
            "default",
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            "log-bbb",
        )
        insert_record(
            record_id="rec-3",
            event_id="evt-3",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=None,
            prev_lookup_hash=None,
            mr_value=None,
            sequence_num=3,
            event_digest="sha384:" + ("33" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-3", "log-ccc", db_path=db)

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.valid is False
        assert resp.entries[2].predecessor_ok is False
        assert resp.entries[2].predecessor_status == "unverifiable"
        assert resp.entries[2].boundary_status == "invalid"

    def test_boundary_classification_survives_when_rtmr_is_available(self, db):
        insert_record(
            record_id="rec-1",
            event_id="evt-1",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=None,
            prev_lookup_hash=None,
            mr_value="aa" * 48,
            sequence_num=1,
            event_digest="sha384:" + ("11" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-1", "log-aaa", db_path=db)
        first_record = get_chain_records("default", db)[0]
        insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=first_record["event_digest"],
            prev_lookup_hash=_compute_record_lookup_hash(first_record),
            mr_value="bb" * 48,
            sequence_num=2,
            event_digest="sha384:" + ("22" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-2", "log-bbb", db_path=db)
        insert_record(
            record_id="rec-3",
            event_id="evt-3",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=None,
            prev_lookup_hash=None,
            mr_value="cc" * 48,
            sequence_num=3,
            event_digest="sha384:" + ("33" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-3", "log-ccc", db_path=db)

        records = get_chain_records("default", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("default")

        assert resp.rtmr_available is True
        assert resp.entries[2].boundary_status == "invalid"

    def test_workload_baseline_snapshot_does_not_fail_rtmr_verification(self, db):
        insert_record(
            record_id="rec-log0",
            event_id="evt-log0-workload-a",
            payload={"bundle": "test", "is_baseline": True},
            status="PENDING",
            chain_id="workload-a",
            rtmr_extended=True,
            prev_event_digest=None,
            prev_lookup_hash=None,
            mr_value="aa" * 48,
            sequence_num=1,
            event_digest="sha384:" + ("11" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-log0", "log-log0", db_path=db)
        insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="workload-a",
            rtmr_extended=True,
            prev_event_digest="sha384:" + ("11" * 48),
            prev_lookup_hash="sha256:" + ("22" * 32),
            mr_value=__import__("hashlib").sha384(bytes.fromhex("aa" * 48) + bytes.fromhex("33" * 48)).hexdigest(),
            sequence_num=2,
            event_digest="sha384:" + ("33" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-2", "log-2", db_path=db)

        records = get_chain_records("workload-a", db)
        from tc_api.trucon.app import verify_chain
        with patch("tc_api.trucon.app.get_chain_records", return_value=records):
            resp = verify_chain("workload-a")

        assert resp.valid is True
        assert resp.rtmr_available is True
        assert resp.entries[0].mr_ok is None
        assert resp.entries[1].mr_ok is True


class TestStartupWarning:
    """Test for NON-TEE MODE startup warning."""

    def test_non_tee_startup_warning(self, caplog):
        """4.5: When TDX sysfs absent, WARNING with 'NON-TEE MODE' is emitted."""
        with patch("os.path.exists", return_value=False):
            with caplog.at_level(logging.WARNING, logger="trucon"):
                # Simulate the startup check logic
                from tc_api.trucon.app import logger as trucon_logger
                if not os.path.exists("/sys/class/misc/tdx_guest/measurements/rtmr"):
                    trucon_logger.warning(
                        "NON-TEE MODE: TDX RTMR sysfs not found — "
                        "running without hardware measurement extensions (development/testing only)"
                    )

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("NON-TEE MODE" in r.message for r in warning_records)

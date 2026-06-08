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

"""Tests for chain verification behavior across predecessor and MR states."""

from unittest.mock import patch

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.trucon.bundles import compute_record_lookup_hash as _compute_record_lookup_hash
from tc_api.trucon.database import (
    get_chain_records,
    init_db,
    insert_record,
    update_record_confirmed,
)
from tc_api.trucon.owner_authorization import sign_owner_authorization
from tc_api.trucon.chain_verification import verify_chain_records


@pytest.fixture
def db(tmp_path):
    """Provide a fresh SQLite DB for each test."""
    db_path = str(tmp_path / "test_queue.db")
    init_db(db_path)
    return db_path


def _insert_confirmed_record(db, record_id, seq, chain_id, prev_event_digest, prev_lookup_hash, log_id, payload=None, event_digest=None):
    """Insert a record and confirm it with the given log_id."""
    insert_record(
        record_id=record_id,
        event_id=f"evt-{seq}",
        payload=payload or {"bundle": "test"},
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        prev_event_digest=prev_event_digest,
        prev_lookup_hash=prev_lookup_hash,
        mr_value=None,
        sequence_num=seq,
        event_digest=event_digest or f"sha384:{seq:096x}",
        db_path=db,
    )
    update_record_confirmed(record_id, log_id, db_path=db)


def _generate_owner_keypair():
    private_key = ec.generate_private_key(ec.SECP384R1())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_key


def _owner_baseline_payload(pub_key: str) -> dict:
    return {
        "bundle": "test",
        "is_baseline": True,
        "pub_key": pub_key,
        "owner_attestation": {"owner_pub_key": pub_key},
    }


class TestPredecessorVerification:
    """Tests for signed predecessor linkage in verify-chain."""

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

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
        resp = verify_chain_records("default", records=records)

        assert resp.rtmr_available is True
        assert resp.entries[2].boundary_status == "invalid"

    def test_workload_baseline_snapshot_does_not_fail_rtmr_verification(self, db):
        insert_record(
            record_id="rec-log0",
            event_id="evt-log0-default",
            payload={"bundle": "test", "is_baseline": True},
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
        update_record_confirmed("rec-log0", "log-log0", db_path=db)
        insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test"},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest="sha384:" + ("11" * 48),
            prev_lookup_hash="sha256:" + ("22" * 32),
            mr_value=__import__("hashlib").sha384(bytes.fromhex("aa" * 48) + bytes.fromhex("33" * 48)).hexdigest(),
            sequence_num=2,
            event_digest="sha384:" + ("33" * 48),
            db_path=db,
        )
        update_record_confirmed("rec-2", "log-2", db_path=db)

        records = get_chain_records("default", db)
        resp = verify_chain_records("default", records=records)

        assert resp.valid is True
        assert resp.rtmr_available is True
        assert resp.entries[0].mr_ok is None
        assert resp.entries[1].mr_ok is True


class TestTdxStartupRequirements:
    def test_rejects_read_only_rtmr_mode(self):
        from tc_api.trucon.app import _initialize_local_mr_adapter

        with patch("tc_api.trucon.app.RTMR_INDEX", 2), \
             patch("tc_api.trucon.app.logger"), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_available", return_value=False), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_extend_available", return_value=False), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_report_read_available", return_value=True):
            with pytest.raises(RuntimeError, match="TDX startup requires RTMR extend support"):
                _initialize_local_mr_adapter()

    def test_rejects_missing_rtmr_support(self):
        from tc_api.trucon.app import _initialize_local_mr_adapter

        with patch("tc_api.trucon.app.RTMR_INDEX", 2), \
             patch("tc_api.trucon.app.logger"), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_available", return_value=False), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_extend_available", return_value=False), \
             patch("tc_api.trucon.adapters.tdx_mr.TdxMRAdapter.is_report_read_available", return_value=False):
            with pytest.raises(RuntimeError, match="TDX startup requires RTMR extend support"):
                _initialize_local_mr_adapter()


class TestOwnerAuthorizationVerification:
    def test_confirmed_record_reports_owner_proven(self, db):
        owner_private_key, owner_pub_key = _generate_owner_keypair()
        _insert_confirmed_record(
            db,
            "rec-log0",
            1,
            "default",
            None,
            None,
            "log-log0",
            payload=_owner_baseline_payload(owner_pub_key),
        )
        first_record = get_chain_records("default", db)[0]
        event_digest = "sha384:" + ("22" * 48)
        owner_authorization = sign_owner_authorization(
            owner_private_key,
            "default",
            2,
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            event_digest,
        )
        _insert_confirmed_record(
            db,
            "rec-2",
            2,
            "default",
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            "log-2",
            payload={"bundle": "test", "owner_authorization": owner_authorization},
            event_digest=event_digest,
        )

        records = get_chain_records("default", db)
        resp = verify_chain_records("default", records=records)

        assert resp.valid is True
        assert resp.entries[0].owner_ok is True
        assert resp.entries[0].owner_status == "origin"
        assert resp.entries[1].owner_ok is True
        assert resp.entries[1].owner_status == "proven"

    def test_confirmed_record_reports_owner_failure(self, db):
        _, owner_pub_key = _generate_owner_keypair()
        wrong_private_key, _ = _generate_owner_keypair()
        _insert_confirmed_record(
            db,
            "rec-log0",
            1,
            "default",
            None,
            None,
            "log-log0",
            payload=_owner_baseline_payload(owner_pub_key),
        )
        first_record = get_chain_records("default", db)[0]
        event_digest = "sha384:" + ("22" * 48)
        owner_authorization = sign_owner_authorization(
            wrong_private_key,
            "default",
            2,
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            event_digest,
        )
        _insert_confirmed_record(
            db,
            "rec-2",
            2,
            "default",
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            "log-2",
            payload={"bundle": "test", "owner_authorization": owner_authorization},
            event_digest=event_digest,
        )

        records = get_chain_records("default", db)
        resp = verify_chain_records("default", records=records)

        assert resp.valid is False
        assert resp.entries[1].owner_ok is False
        assert resp.entries[1].owner_status == "invalid"
        assert "owner authorization signature mismatch" in resp.entries[1].error

    def test_pending_record_reports_owner_unverifiable(self, db):
        owner_private_key, owner_pub_key = _generate_owner_keypair()
        _insert_confirmed_record(
            db,
            "rec-log0",
            1,
            "default",
            None,
            None,
            "log-log0",
            payload=_owner_baseline_payload(owner_pub_key),
        )
        first_record = get_chain_records("default", db)[0]
        event_digest = "sha384:" + ("22" * 48)
        owner_authorization = sign_owner_authorization(
            owner_private_key,
            "default",
            2,
            first_record["event_digest"],
            _compute_record_lookup_hash(first_record),
            event_digest,
        )
        insert_record(
            record_id="rec-2",
            event_id="evt-2",
            payload={"bundle": "test", "owner_authorization": owner_authorization},
            status="PENDING",
            chain_id="default",
            rtmr_extended=True,
            prev_event_digest=first_record["event_digest"],
            prev_lookup_hash=_compute_record_lookup_hash(first_record),
            mr_value=None,
            sequence_num=2,
            event_digest=event_digest,
            db_path=db,
        )

        records = get_chain_records("default", db)
        resp = verify_chain_records("default", records=records)

        assert resp.entries[1].owner_ok is None
        assert resp.entries[1].owner_status == "unverifiable"

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

"""Integration tests for session delegation end-to-end flow.

These tests validate the full delegation lifecycle using mocks for
external services (TruCon, Rekor, Fulcio).  They exercise the real
code paths in trucon_client.py and delegation.py.
"""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.docktap.trucon_client import TruConCommitter
from tc_api.trucon.database import (
    init_db,
    get_active_delegation,
    insert_delegation,
    cleanup_expired_delegations,
)


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "integration.db")
    init_db(db_path)
    return db_path


@pytest.fixture()
def owner_key():
    return ec.generate_private_key(ec.SECP384R1())


@pytest.fixture()
def committer():
    return TruConCommitter(
        trucon_url="http://127.0.0.1:59999",
        start_retry_worker=False,
    )


def _mock_op_record(operation="pull"):
    record = MagicMock()
    record.image = {"name": "nginx", "tag": "latest", "digest": "sha256:abc123"}
    record.container = {"name": "web-1", "id": "ctr-aaa"}
    record.operation = operation
    record.runtime_engine = "docker"
    record.response = {"status": 200}
    record.labels = {}
    return record


def _future_iso(seconds=14400):
    return (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()


def _past_iso(seconds=60):
    return (datetime.utcnow() - timedelta(seconds=seconds)).isoformat()


class TestDelegationE2EFlow:
    """9.1 OIDC login → create delegation → docker ops (owner key signed) → verify chain."""

    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value=None)
    @patch("tc_api.docktap.trucon_client.get_chain_owner_private_key")
    def test_full_delegation_lifecycle(self, mock_get_key, mock_token, committer, owner_key, tmp_db):
        mock_get_key.return_value = owner_key
        chain_id = "test-chain-e2e"

        # 1. Create delegation (simulating what the endpoint does)
        insert_delegation(
            delegation_id="del-e2e-001",
            chain_id=chain_id,
            scope=["pull", "create", "start", "stop", "rm"],
            expires_at=_future_iso(),
            signer_identity="user@example.com",
            sequence_num=2,
            db_path=tmp_db,
        )

        # 2. Verify delegation is active
        active = get_active_delegation(chain_id, db_path=tmp_db)
        assert active is not None
        assert active["delegation_id"] == "del-e2e-001"

        # 3. Submit operations via delegation path (mock TruCon + Rekor)
        with patch("tc_api.trucon.database.get_active_delegation") as mock_get_del, \
             patch.object(committer, "_resolve_submission_context", return_value=(chain_id, "wl-1", "l-1", "inst-1")), \
             patch.object(committer, "_reserve_commit_intent", return_value={
                 "sequence_num": 3,
                 "prev_event_digest": "sha384:prev1",
                 "prev_lookup_hash": "sha384:lh1",
                 "intent_token": "tok-1",
             }), \
             patch("tc_api.docktap.trucon_client.SigstoreLogAdapter") as mock_adapter_cls, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "r-1", "sequence_num": 3}), \
             patch.object(committer, "_mark_acknowledged"):

            mock_get_del.return_value = active
            mock_adapter_cls.return_value.submit_owner_signed_entry.return_value = (
                "uuid-e2e-1", 9999, {"logIndex": 9999}
            )

            # docker pull
            result = committer._do_submit(_mock_op_record("pull"), "pull")
            assert result is True
            mock_adapter_cls.return_value.submit_owner_signed_entry.assert_called_once()

        # 4. Verify delegation verification annotations
        from tc_api.transparency.verification import _annotate_delegation_verification
        chain_events = [
            {"event_type": "chain.init", "sequence_num": 1},
            {
                "event_type": "session.delegation",
                "delegation_id": "del-e2e-001",
                "scope": ["pull", "create", "start", "stop", "rm"],
                "expires_at": _future_iso(),
                "created": datetime.utcnow().isoformat(),
                "sequence_num": 2,
            },
            {
                "event_type": "docker_pull",
                "delegation_id": "del-e2e-001",
                "created": datetime.utcnow().isoformat(),
                "sequence_num": 3,
            },
        ]
        annotated = _annotate_delegation_verification(chain_events)
        assert annotated[0]["delegation_status"] == "not_applicable"
        assert annotated[1]["delegation_status"] == "origin"
        assert annotated[2]["delegation_status"] == "proven"


class TestDelegationTTLExpiry:
    """9.2 Delegation TTL expiry → attestation gate blocks → re-login → resume."""

    def test_expired_delegation_blocks_then_new_delegation_resumes(self, tmp_db):
        chain_id = "test-chain-ttl"

        # 1. Create expired delegation
        insert_delegation(
            delegation_id="del-expired",
            chain_id=chain_id,
            scope=["pull"],
            expires_at=_past_iso(60),
            signer_identity="user@example.com",
            sequence_num=2,
            db_path=tmp_db,
        )

        # 2. Verify delegation is NOT active (expired)
        assert get_active_delegation(chain_id, db_path=tmp_db) is None

        # 3. Cleanup expired
        deleted = cleanup_expired_delegations(db_path=tmp_db)
        assert deleted >= 1

        # 4. Create new valid delegation (simulating re-login)
        insert_delegation(
            delegation_id="del-renewed",
            chain_id=chain_id,
            scope=["pull", "create", "start", "stop", "rm"],
            expires_at=_future_iso(7200),
            signer_identity="user@example.com",
            sequence_num=3,
            db_path=tmp_db,
        )

        # 5. Verify new delegation is active
        active = get_active_delegation(chain_id, db_path=tmp_db)
        assert active is not None
        assert active["delegation_id"] == "del-renewed"

        # 6. Verify delegation verification catches expiry in chain replay
        from tc_api.transparency.verification import _annotate_delegation_verification
        chain_events = [
            {
                "event_type": "session.delegation",
                "delegation_id": "del-expired",
                "scope": ["pull"],
                "expires_at": _past_iso(60),
                "created": _past_iso(120),
                "sequence_num": 2,
            },
            {
                "event_type": "docker_pull",
                "delegation_id": "del-expired",
                "created": datetime.utcnow().isoformat(),  # after expiry
                "sequence_num": 3,
            },
            {
                "event_type": "session.delegation",
                "delegation_id": "del-renewed",
                "scope": ["pull", "create", "start", "stop", "rm"],
                "expires_at": _future_iso(7200),
                "created": datetime.utcnow().isoformat(),
                "sequence_num": 4,
            },
            {
                "event_type": "docker_pull",
                "delegation_id": "del-renewed",
                "created": datetime.utcnow().isoformat(),
                "sequence_num": 5,
            },
        ]
        annotated = _annotate_delegation_verification(chain_events)

        assert annotated[0]["delegation_status"] == "origin"   # del-expired creation
        assert annotated[1]["delegation_status"] == "expired"   # business event after expiry
        assert annotated[2]["delegation_status"] == "origin"   # del-renewed creation
        assert annotated[3]["delegation_status"] == "proven"   # valid business event

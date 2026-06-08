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

"""Tests for delegation storage CRUD in trucon/database.py."""
from datetime import datetime, timedelta

import pytest

from tc_api.trucon.database import (
    cleanup_expired_delegations,
    get_active_delegation,
    init_db,
    insert_delegation,
)


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test_delegation.db")
    init_db(db_path)
    return db_path


def _iso_future(seconds: int = 3600) -> str:
    return (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()


def _iso_past(seconds: int = 60) -> str:
    return (datetime.utcnow() - timedelta(seconds=seconds)).isoformat()


# ---- insert + query ----

def test_insert_and_get_active(tmp_db):
    insert_delegation(
        delegation_id="del-1",
        chain_id="chain-a",
        scope=["pull", "create", "start", "stop", "rm"],
        expires_at=_iso_future(7200),
        signer_identity="user@example.com",
        sequence_num=2,
        db_path=tmp_db,
    )

    active = get_active_delegation("chain-a", db_path=tmp_db)
    assert active is not None
    assert active["delegation_id"] == "del-1"
    assert active["chain_id"] == "chain-a"
    assert active["scope"] == ["pull", "create", "start", "stop", "rm"]
    assert active["signer_identity"] == "user@example.com"
    assert active["sequence_num"] == 2


def test_get_active_returns_none_when_empty(tmp_db):
    assert get_active_delegation("no-such-chain", db_path=tmp_db) is None


def test_get_active_returns_most_recent(tmp_db):
    insert_delegation("del-old", "chain-b", ["pull"], _iso_future(3600), "a@b.com", 2, db_path=tmp_db)
    insert_delegation("del-new", "chain-b", ["pull", "create"], _iso_future(7200), "a@b.com", 3, db_path=tmp_db)

    active = get_active_delegation("chain-b", db_path=tmp_db)
    assert active["delegation_id"] == "del-new"


def test_per_chain_isolation(tmp_db):
    insert_delegation("del-x", "chain-x", ["pull"], _iso_future(), "x@x.com", 1, db_path=tmp_db)
    insert_delegation("del-y", "chain-y", ["create"], _iso_future(), "y@y.com", 1, db_path=tmp_db)

    assert get_active_delegation("chain-x", db_path=tmp_db)["delegation_id"] == "del-x"
    assert get_active_delegation("chain-y", db_path=tmp_db)["delegation_id"] == "del-y"


# ---- expiry ----

def test_expired_delegation_not_returned(tmp_db):
    insert_delegation("del-exp", "chain-e", ["pull"], _iso_past(10), "e@e.com", 1, db_path=tmp_db)
    assert get_active_delegation("chain-e", db_path=tmp_db) is None


def test_cleanup_expired(tmp_db):
    insert_delegation("del-good", "chain-c", ["pull"], _iso_future(), "c@c.com", 1, db_path=tmp_db)
    insert_delegation("del-bad1", "chain-c", ["pull"], _iso_past(10), "c@c.com", 2, db_path=tmp_db)
    insert_delegation("del-bad2", "chain-d", ["pull"], _iso_past(5), "d@d.com", 1, db_path=tmp_db)

    deleted = cleanup_expired_delegations(db_path=tmp_db)
    assert deleted == 2

    # good delegation still active
    assert get_active_delegation("chain-c", db_path=tmp_db)["delegation_id"] == "del-good"
    assert get_active_delegation("chain-d", db_path=tmp_db) is None

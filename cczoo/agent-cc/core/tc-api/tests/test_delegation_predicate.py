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

"""Tests for delegation predicate builder and endpoint logic."""
from datetime import datetime
from unittest.mock import patch

from tc_api.docktap.delegation import (
    build_delegation_predicate,
    DEFAULT_SCOPE,
)


class TestBuildDelegationPredicate:
    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    def test_returns_required_fields(self, _mock_key):
        pred, event_digest, delegation_id, expires_at = build_delegation_predicate(
            chain_id="chain-test",
            sequence_num=5,
            prev_event_digest="sha384:abc",
            prev_lookup_hash="sha384:def",
        )
        assert pred["event_type"] == "session.delegation"
        assert pred["chain_id"] == "chain-test"
        assert pred["sequence_num"] == 5
        assert pred["prev_event_digest"] == "sha384:abc"
        assert pred["prev_lookup_hash"] == "sha384:def"
        assert pred["delegation_id"] == delegation_id
        assert pred["expires_at"] == expires_at
        assert pred["scope"] == DEFAULT_SCOPE
        assert "digest" in pred
        assert event_digest == pred["digest"]

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    @patch("tc_api.docktap.delegation.delegation_scope", return_value=["pull", "create"])
    def test_uses_service_default_scope_when_scope_omitted(self, _mock_scope, _mock_key):
        pred, _, _, _ = build_delegation_predicate(
            chain_id="chain-test",
            sequence_num=5,
            prev_event_digest="sha384:abc",
            prev_lookup_hash="sha384:def",
        )
        assert pred["scope"] == ["pull", "create"]

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    def test_custom_scope(self, _mock_key):
        pred, _, _, _ = build_delegation_predicate(
            chain_id="c", sequence_num=1,
            prev_event_digest=None, prev_lookup_hash=None,
            scope=["pull", "create"],
        )
        assert pred["scope"] == ["pull", "create"]

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    def test_custom_ttl(self, _mock_key):
        pred, _, _, expires_at = build_delegation_predicate(
            chain_id="c", sequence_num=1,
            prev_event_digest=None, prev_lookup_hash=None,
            ttl_seconds=120,
        )
        created = datetime.fromisoformat(pred["created"])
        exp = datetime.fromisoformat(expires_at)
        delta = (exp - created).total_seconds()
        assert 119 <= delta <= 121

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    @patch("tc_api.docktap.delegation.DOCKTAP_DELEGATION_TTL_SECONDS", 90)
    def test_uses_service_default_ttl_when_ttl_omitted(self, _mock_key):
        pred, _, _, expires_at = build_delegation_predicate(
            chain_id="c", sequence_num=1,
            prev_event_digest=None, prev_lookup_hash=None,
        )
        created = datetime.fromisoformat(pred["created"])
        exp = datetime.fromisoformat(expires_at)
        delta = (exp - created).total_seconds()
        assert 89 <= delta <= 91

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key")
    def test_owner_authorization_added(self, mock_key):
        from cryptography.hazmat.primitives.asymmetric import ec
        mock_key.return_value = ec.generate_private_key(ec.SECP384R1())

        pred, _, _, _ = build_delegation_predicate(
            chain_id="c", sequence_num=2,
            prev_event_digest="sha384:prev", prev_lookup_hash="sha384:lh",
        )
        assert "owner_authorization" in pred
        assert pred["owner_authorization"]["algorithm"] == "ecdsa-p384-sha384"

    @patch("tc_api.docktap.delegation.get_chain_owner_private_key", return_value=None)
    def test_entries_contain_delegation_fields(self, _mock_key):
        pred, _, delegation_id, expires_at = build_delegation_predicate(
            chain_id="c", sequence_num=1,
            prev_event_digest=None, prev_lookup_hash=None,
        )
        entry_keys = [e["key"] for e in pred["entries"]]
        assert "delegation_id" in entry_keys
        assert "scope" in entry_keys
        assert "expires_at" in entry_keys

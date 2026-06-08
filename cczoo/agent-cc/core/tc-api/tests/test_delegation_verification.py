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

"""Tests for _annotate_delegation_verification in tlog_client.py."""
from tc_api.transparency.verification import _annotate_delegation_verification


def _make_delegation_event(delegation_id="del-1", scope=None, expires_at="2099-01-01T00:00:00"):
    return {
        "event_type": "session.delegation",
        "delegation_id": delegation_id,
        "scope": scope or ["pull", "create", "start", "stop", "rm"],
        "expires_at": expires_at,
        "created": "2025-06-01T00:00:00",
        "signer_identity": "user@example.com",
        "sequence_num": 2,
    }


def _make_business_event(delegation_id=None, event_type="docker_pull", created="2025-06-01T01:00:00"):
    entry = {
        "event_type": event_type,
        "created": created,
        "sequence_num": 3,
    }
    if delegation_id:
        entry["delegation_id"] = delegation_id
    return entry


class TestAnnotateDelegationVerification:
    def test_delegation_event_marked_origin(self):
        entries = [_make_delegation_event()]
        result = _annotate_delegation_verification(entries)
        assert result[0]["delegation_status"] == "origin"

    def test_business_event_proven(self):
        entries = [
            _make_delegation_event(delegation_id="del-a"),
            _make_business_event(delegation_id="del-a", event_type="docker_pull"),
        ]
        result = _annotate_delegation_verification(entries)
        assert result[1]["delegation_status"] == "proven"

    def test_business_event_expired(self):
        entries = [
            _make_delegation_event(delegation_id="del-b", expires_at="2025-06-01T00:30:00"),
            _make_business_event(delegation_id="del-b", created="2025-06-01T01:00:00"),
        ]
        result = _annotate_delegation_verification(entries)
        assert result[1]["delegation_status"] == "expired"
        assert any("expiry" in e for e in result[1]["errors"])

    def test_business_event_scope_violation(self):
        entries = [
            _make_delegation_event(delegation_id="del-c", scope=["pull", "create"]),
            _make_business_event(delegation_id="del-c", event_type="docker_rm"),
        ]
        result = _annotate_delegation_verification(entries)
        assert result[1]["delegation_status"] == "scope_violation"
        assert any("scope" in e for e in result[1]["errors"])

    def test_business_event_missing_delegation(self):
        entries = [
            _make_business_event(delegation_id="del-nonexistent"),
        ]
        result = _annotate_delegation_verification(entries)
        assert result[0]["delegation_status"] == "missing"
        assert any("not found" in e for e in result[0]["errors"])

    def test_no_delegation_id_marked_not_applicable(self):
        entries = [_make_business_event()]  # no delegation_id
        result = _annotate_delegation_verification(entries)
        assert result[0]["delegation_status"] == "not_applicable"

    def test_chain_init_not_applicable(self):
        entries = [{"event_type": "chain.init", "sequence_num": 1}]
        result = _annotate_delegation_verification(entries)
        assert result[0]["delegation_status"] == "not_applicable"

    def test_mixed_chain(self):
        """Full chain: init → delegation → business × 2."""
        entries = [
            {"event_type": "chain.init", "sequence_num": 1},
            _make_delegation_event(delegation_id="del-mix"),
            _make_business_event(delegation_id="del-mix", event_type="docker_pull"),
            _make_business_event(delegation_id="del-mix", event_type="docker_create"),
        ]
        result = _annotate_delegation_verification(entries)
        assert result[0]["delegation_status"] == "not_applicable"
        assert result[1]["delegation_status"] == "origin"
        assert result[2]["delegation_status"] == "proven"
        assert result[3]["delegation_status"] == "proven"

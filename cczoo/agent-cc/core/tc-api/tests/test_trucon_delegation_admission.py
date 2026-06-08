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

"""Tests for TruCon /commit endpoint handling owner-key-signed bundles."""

import base64
import json
import time
from unittest.mock import MagicMock

import pytest

from tc_api.trucon.bundles import extract_bundle_payload, extract_bundle_payload_b64, extract_bundle_predicate
from tc_api.trucon.submit_daemon import SubmitDaemon


def _make_owner_key_bundle(predicate: dict) -> str:
    """Build a minimal owner-key-signed bundle JSON string."""
    statement = {
        "_type": "https://in-toto.io/Statement/v0.1",
        "subject": [{"name": "test", "digest": {"sha384": "a" * 96}}],
        "predicateType": "https://trusted-log.dev/v1",
        "predicate": predicate,
    }
    payload_b64 = base64.b64encode(json.dumps(statement).encode()).decode()
    envelope = {
        "payloadType": "application/vnd.in-toto+json",
        "payload": payload_b64,
        "signatures": [{"sig": "dGVzdA=="}],
    }
    return json.dumps({
        "_owner_key_signed": True,
        "envelope": envelope,
        "pub_key_pem": "-----BEGIN PUBLIC KEY-----\ntest\n-----END PUBLIC KEY-----\n",
        "rekor_uuid": "uuid-123",
        "rekor_log_index": 42,
    })


class TestOwnerKeyBundleExtraction:
    def test_extract_payload_from_owner_key_bundle(self):
        pred = {"event_id": "evt-1", "event_type": "docker_pull", "chain_id": "c1"}
        bundle_json = _make_owner_key_bundle(pred)
        payload = extract_bundle_payload(bundle_json)
        assert payload["predicate"]["event_id"] == "evt-1"
        assert payload["predicate"]["chain_id"] == "c1"

    def test_extract_predicate_from_owner_key_bundle(self):
        pred = {"event_id": "evt-2", "event_type": "session.delegation", "delegation_id": "del-1"}
        bundle_json = _make_owner_key_bundle(pred)
        predicate = extract_bundle_predicate(bundle_json)
        assert predicate["event_type"] == "session.delegation"
        assert predicate["delegation_id"] == "del-1"

    def test_extract_payload_b64_from_owner_key_bundle(self):
        pred = {"event_id": "evt-3", "event_type": "docker_pull", "chain_id": "c1"}
        bundle_json = _make_owner_key_bundle(pred)
        payload_b64 = extract_bundle_payload_b64(bundle_json)
        statement = json.loads(base64.b64decode(payload_b64).decode())

        assert statement["predicate"]["event_id"] == "evt-3"

    def test_missing_payload_raises(self):
        bundle_json = json.dumps({
            "_owner_key_signed": True,
            "envelope": {"payloadType": "test"},
        })
        with pytest.raises(ValueError, match="missing payload"):
            extract_bundle_payload(bundle_json)


def test_submit_daemon_treats_owner_key_submission_as_preconfirmed():
    immutable_log = MagicMock()
    daemon = SubmitDaemon(immutable_log=immutable_log, bundle_mirror=None, heartbeat_ticks=1)
    daemon._confirm_record = MagicMock()
    bundle_json = _make_owner_key_bundle({"event_id": "evt-4", "event_type": "docker_pull", "chain_id": "c1"})

    daemon._submit_record(
        {
            "record_id": "rec-1",
            "chain_id": "c1",
            "sequence_num": 3,
            "event_id": "evt-4",
            "payload": json.dumps({"bundle": bundle_json}),
        },
        "rec-1",
        "c1",
        3,
        bundle_json,
        time.perf_counter(),
    )

    immutable_log.submit_bundle.assert_not_called()
    daemon._confirm_record.assert_called_once()
    assert daemon._confirm_record.call_args.args[4] == "uuid-123"
    assert daemon._confirm_record.call_args.args[6]["logIndex"] == 42

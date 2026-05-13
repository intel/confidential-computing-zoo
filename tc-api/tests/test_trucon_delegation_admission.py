"""Tests for TruCon /commit endpoint handling owner-key-signed bundles."""
import base64
import json

import pytest

from tc_api.trucon.app import _extract_bundle_payload, _extract_bundle_predicate


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
        payload = _extract_bundle_payload(bundle_json)
        assert payload["predicate"]["event_id"] == "evt-1"
        assert payload["predicate"]["chain_id"] == "c1"

    def test_extract_predicate_from_owner_key_bundle(self):
        pred = {"event_id": "evt-2", "event_type": "session.delegation", "delegation_id": "del-1"}
        bundle_json = _make_owner_key_bundle(pred)
        predicate = _extract_bundle_predicate(bundle_json)
        assert predicate["event_type"] == "session.delegation"
        assert predicate["delegation_id"] == "del-1"

    def test_missing_payload_raises(self):
        bundle_json = json.dumps({
            "_owner_key_signed": True,
            "envelope": {"payloadType": "test"},
        })
        with pytest.raises(ValueError, match="missing payload"):
            _extract_bundle_payload(bundle_json)

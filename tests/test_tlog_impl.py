import pytest
from unittest.mock import patch, MagicMock
import base64
import json

from sigstore.models import Bundle
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter
from tc_api.tlog_client import TrustedLogAPI

@pytest.fixture
def mock_rekor():
    with patch("sigstore._internal.rekor.client.RekorClient") as MockClient:
        yield MockClient

def test_sigstore_adapter_submit_bundle(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_bundle = MagicMock(spec=Bundle)
    
    # Mocking the client method
    mock_instance = mock_rekor.return_value
    mock_instance.log.entries.post.return_value = {"log-id-123": {}}

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "log-id-123"
    assert status == "confirmed"

def test_sigstore_adapter_get_entry(mock_rekor):
    adapter = SigstoreLogAdapter()

    mock_instance = mock_rekor.return_value
    mock_instance.log.entries.get.return_value = {"body": "test"}

    entry = adapter.get_entry("log-id-123")
    assert entry == {"body": "test"}
    mock_instance.log.entries.get.assert_called_with("log-id-123")

def test_sigstore_adapter_traverse(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_instance = mock_rekor.return_value

    # fake body spec payload
    def make_entry(prev_id):
        payload = {"predicate": {"prev_log_id": prev_id}}
        enc_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
        return {"body": {"spec": {"payload": enc_payload}}}

    mock_instance.log.entries.get.side_effect = [
        {"id-2": make_entry("id-1")},
        {"id-1": make_entry(None)},
        None
    ]

    results = adapter.traverse("id-2", count=5)
    
    # Expecting 2 results before it hit None link
    assert len(results) == 2


class StubImmutableLog:
    def __init__(self, entries=None, error=None):
        self._entries = entries or []
        self._error = error

    def submit_bundle(self, bundle, prev_log_id=None):
        raise NotImplementedError()

    def get_entry(self, log_id):
        raise NotImplementedError()

    def traverse(self, end_log_id, count=10):
        if self._error:
            raise self._error
        return self._entries


def _make_rekor_entry(event_id: str, event_type: str = "commit"):
    payload = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "event_id": event_id,
            "event_type": event_type,
            "digest": f"sha384:{event_id}",
        },
    }
    enc_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {"body": {"spec": {"payload": enc_payload}}}


def test_verify_record_returns_structured_entry_details():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[_make_rekor_entry("evt-1"), _make_rekor_entry("evt-2")]))

    with patch("tc_api.tlog_client._extract_signer_identity", side_effect=["alice@example.com", "alice@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["source"] == "immutable_backend"
    assert result.details["entry_count"] == 2
    assert result.details["observed_entry_count"] == 2
    assert result.details["applied_signer_identity"] == "alice@example.com"
    assert len(result.details["entries"]) == 2
    assert result.details["entries"][0]["event_id"] == "evt-1"
    assert result.details["entries"][0]["signer_identity_match"] is True


def test_verify_record_filters_by_signer_identity():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[_make_rekor_entry("evt-1"), _make_rekor_entry("evt-2")]))

    with patch("tc_api.tlog_client._extract_signer_identity", side_effect=["alice@example.com", "bob@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entry_count"] == 1
    assert result.details["filtered_out_count"] == 1
    assert result.details["entries"][0]["event_id"] == "evt-1"


def test_verify_record_fails_on_expected_entry_count_mismatch():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[_make_rekor_entry("evt-1")]))

    with patch("tc_api.tlog_client._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record(
            "tail-log-id",
            policy={
                "chain_id": "default",
                "signer_identity": "alice@example.com",
                "expected_entry_count": 2,
            },
        )

    assert result.success is False
    assert result.errors == ["Expected 2 entries, got 1"]
    assert result.details["expected_entry_count"] == 2
    assert result.details["entry_count"] == 1


def test_verify_record_returns_structured_failure_details():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(error=RuntimeError("rekor unavailable")))

    result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is False
    assert result.errors == ["rekor unavailable"]
    assert result.details["source"] == "immutable_backend"
    assert result.details["entries"] == []

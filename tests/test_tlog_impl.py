import pytest
from unittest.mock import patch, MagicMock

from sigstore.models import Bundle
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter

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
    
    import base64
    import json
    
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

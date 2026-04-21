import pytest
from unittest.mock import patch, MagicMock
import base64
import json
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from sigstore.models import Bundle
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter
from tc_api.tlog_client import TrustedLogAPI, _decode_dsse_payload, _extract_signer_identity

@pytest.fixture
def mock_rekor():
    SigstoreLogAdapter._bundle_entry_cache.clear()
    with patch("sigstore._internal.rekor.client.RekorClient") as MockClient:
        yield MockClient
    SigstoreLogAdapter._bundle_entry_cache.clear()

def test_sigstore_adapter_submit_bundle(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.log_entry.log_index = 123
    mock_bundle.log_entry.uuid = None

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "123"
    assert status == "confirmed"
    assert receipt is mock_bundle.log_entry
    mock_rekor.return_value.log.entries.post.assert_not_called()


def test_sigstore_adapter_submit_bundle_posts_dsse_when_bundle_has_no_log_reference(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.log_entry.log_index = None
    mock_bundle.log_entry.uuid = None
    mock_bundle._dsse_envelope.to_json.return_value = '{"payload":"x"}'
    mock_bundle.signing_certificate.public_bytes.return_value = b"pem-cert"

    mock_entry = MagicMock()
    mock_entry.uuid = "log-id-123"
    mock_rekor.return_value.log.entries.post.return_value = mock_entry

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "log-id-123"
    assert status == "confirmed"
    assert receipt is mock_entry
    mock_rekor.return_value.log.entries.post.assert_called_once()

def test_sigstore_adapter_get_entry(mock_rekor):
    adapter = SigstoreLogAdapter()

    mock_instance = mock_rekor.return_value
    mock_instance.log.entries.get.return_value = {"body": "test"}

    entry = adapter.get_entry("log-id-123")
    assert entry == {"body": "test"}
    mock_instance.log.entries.get.assert_called_with(uuid="log-id-123")


def test_sigstore_adapter_get_entry_by_log_index(mock_rekor):
    adapter = SigstoreLogAdapter()

    mock_instance = mock_rekor.return_value
    mock_instance.log.entries.get.return_value = {"body": "test"}

    entry = adapter.get_entry("123")
    assert entry == {"body": "test"}
    mock_instance.log.entries.get.assert_called_with(log_index=123)


def test_sigstore_adapter_reuses_cached_bundle_entry_across_instances(mock_rekor):
    adapter_submit = SigstoreLogAdapter()
    adapter_verify = SigstoreLogAdapter()
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.log_entry.log_index = 123
    mock_bundle.log_entry.uuid = None

    statement = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {"event_id": "evt-cache", "prev_log_id": None},
    }
    envelope = {
        "payloadType": "application/vnd.in-toto+json",
        "payload": base64.b64encode(json.dumps(statement).encode("utf-8")).decode("utf-8"),
        "signatures": [{"sig": "abc"}],
    }
    mock_bundle._dsse_envelope.to_json.return_value = json.dumps(envelope)
    mock_bundle.signing_certificate.public_bytes.return_value = b"pem-cert"

    log_id, status, _receipt = adapter_submit.submit_bundle(mock_bundle)
    cached_entry = adapter_verify.get_entry(log_id)

    assert status == "confirmed"
    assert log_id == "123"
    assert cached_entry["body"]["spec"]["payload"] == envelope["payload"]
    mock_rekor.return_value.log.entries.get.assert_not_called()

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


def test_sigstore_adapter_traverse_keeps_normalized_entry_dict(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_instance = mock_rekor.return_value

    payload = {"predicate": {"event_id": "evt-1", "prev_log_id": None}}
    enc_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    mock_instance.log.entries.get.return_value = {
        "uuid": "id-1",
        "body": {"spec": {"payload": enc_payload}},
    }

    results = adapter.traverse("id-1", count=1)

    assert len(results) == 1
    assert results[0]["uuid"] == "id-1"
    assert isinstance(results[0], dict)


def _make_test_cert_b64(email: str) -> str:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"test-signer"),
        x509.NameAttribute(NameOID.EMAIL_ADDRESS, email),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(minutes=10))
        .add_extension(
            x509.SubjectAlternativeName([x509.RFC822Name(email)]),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    return base64.b64encode(cert_pem).decode("utf-8")


def test_extract_signer_identity_from_dsse_verifier():
    cert_b64 = _make_test_cert_b64("alice@example.com")
    entry = {
        "body": {
            "spec": {
                "signatures": [
                    {"signature": "abc", "verifier": cert_b64}
                ]
            }
        }
    }

    assert _extract_signer_identity(entry) == "alice@example.com"


def test_extract_signer_identity_from_proposed_content_verifiers_fallback():
    cert_b64 = _make_test_cert_b64("bob@example.com")
    entry = {
        "body": {
            "spec": {
                "proposedContent": {
                    "verifiers": [cert_b64]
                }
            }
        }
    }

    assert _extract_signer_identity(entry) == "bob@example.com"


def test_decode_dsse_payload_from_proposed_content_envelope():
    statement = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "event_id": "evt-123",
            "event_type": "launch",
            "digest": "sha384:deadbeef",
            "entries": [{"key": "operation_result", "value": "success"}],
        },
    }
    envelope = {
        "payloadType": "application/vnd.in-toto+json",
        "payload": base64.b64encode(json.dumps(statement).encode("utf-8")).decode("utf-8"),
        "signatures": [{"sig": "abc"}],
    }
    body = {
        "spec": {
            "proposedContent": {
                "envelope": json.dumps(envelope),
                "verifiers": [],
            }
        }
    }

    decoded = _decode_dsse_payload(body)

    assert decoded["predicate"]["event_id"] == "evt-123"
    assert decoded["predicate"]["digest"] == "sha384:deadbeef"


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

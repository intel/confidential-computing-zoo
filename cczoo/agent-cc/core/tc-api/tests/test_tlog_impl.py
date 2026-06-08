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

import pytest
from unittest.mock import patch, MagicMock
import base64
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from sigstore.models import Bundle
from tlog.backends.rekor.oci_mirror import OciBundleMirror
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from tc_api.transparency.commit_client import TrustedLogAPI
from tc_api.transparency.verification import _decode_dsse_payload, _extract_signer_identity
from tc_api.trucon.owner_authorization import sign_owner_authorization

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
    mock_bundle.log_entry.body = base64.b64encode(
        json.dumps({"kind": "intoto", "spec": {}}).encode("utf-8")
    ).decode("utf-8")

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "123"
    assert status == "confirmed"
    assert receipt is mock_bundle.log_entry
    mock_rekor.return_value.log.entries.post.assert_not_called()


def test_sigstore_adapter_does_not_reuse_existing_dsse_entry_for_intoto_submission(mock_rekor):
    adapter = SigstoreLogAdapter(rekor_entry_type="intoto")
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.log_entry.log_index = 123
    mock_bundle.log_entry.uuid = None
    mock_bundle.log_entry.body = base64.b64encode(
        json.dumps({"kind": "dsse", "spec": {}}).encode("utf-8")
    ).decode("utf-8")
    mock_bundle._dsse_envelope.to_json.return_value = json.dumps(
        {
            "payloadType": "application/vnd.in-toto+json",
            "payload": "e30=",
            "signatures": [{"sig": "abc", "keyid": "test-key"}],
        }
    )
    mock_bundle.signing_certificate.public_bytes.return_value = b"pem-cert"

    mock_entry = MagicMock()
    mock_entry.uuid = "intoto-log-id-123"
    mock_entry.log_index = 456
    mock_rekor.return_value.log.entries.post.return_value = mock_entry

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "intoto-log-id-123"
    assert status == "confirmed"
    assert receipt is mock_entry
    mock_rekor.return_value.log.entries.post.assert_called_once()


def test_sigstore_adapter_submit_bundle_posts_dsse_when_bundle_has_no_log_reference(mock_rekor):
    adapter = SigstoreLogAdapter(rekor_entry_type="dsse")
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


def test_sigstore_adapter_submit_bundle_posts_intoto_by_default(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_bundle = MagicMock(spec=Bundle)
    mock_bundle.log_entry.log_index = None
    mock_bundle.log_entry.uuid = None
    mock_bundle._dsse_envelope.to_json.return_value = json.dumps(
        {
            "payloadType": "application/vnd.in-toto+json",
            "payload": "e30=",
            "signatures": [{"sig": "abc", "keyid": "test-key"}],
        }
    )
    mock_bundle.signing_certificate.public_bytes.return_value = b"pem-cert"

    mock_entry = MagicMock()
    mock_entry.uuid = "log-id-456"
    mock_rekor.return_value.log.entries.post.return_value = mock_entry

    log_id, status, receipt = adapter.submit_bundle(mock_bundle)

    assert log_id == "log-id-456"
    assert status == "confirmed"
    assert receipt is mock_entry

    proposed_entry = mock_rekor.return_value.log.entries.post.call_args.args[0]
    dumped = proposed_entry.model_dump(by_alias=True)
    assert dumped["apiVersion"] == "0.0.2"
    assert dumped["kind"] == "intoto"
    assert dumped["spec"]["content"]["envelope"]["payloadType"] == "application/vnd.in-toto+json"
    assert dumped["spec"]["content"]["envelope"]["payload"] == base64.b64encode(b"e30=").decode()
    assert dumped["spec"]["content"]["envelope"]["signatures"][0]["sig"] == base64.b64encode(b"abc").decode()
    assert dumped["spec"]["content"]["envelope"]["signatures"][0]["publicKey"] == base64.b64encode(b"pem-cert").decode()
    assert dumped["spec"]["content"]["hash"] == {
        "algorithm": "sha256",
        "value": hashlib.sha256(mock_bundle._dsse_envelope.to_json.return_value.encode()).hexdigest(),
    }


def test_sigstore_adapter_reads_default_entry_type_from_environment(mock_rekor):
    with patch.dict(os.environ, {"TC_API_REKOR_ENTRY_TYPE": "dsse"}, clear=False):
        adapter = SigstoreLogAdapter()

    assert adapter.rekor_entry_type == "dsse"


def test_sigstore_adapter_rejects_unknown_entry_type(mock_rekor):
    with pytest.raises(ValueError, match="Unsupported Rekor entry type"):
        SigstoreLogAdapter(rekor_entry_type="unknown")

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
    mock_rekor.return_value.log.entries.get.side_effect = RuntimeError("public fetch unavailable")
    cached_entry = adapter_verify.get_entry(log_id)

    assert status == "confirmed"
    assert log_id == "123"
    assert cached_entry["body"]["spec"]["payload"] == envelope["payload"]
    assert cached_entry["_tc_replay_provenance"] == "cache-assisted"
    mock_rekor.return_value.log.entries.get.assert_called_once()


def test_sigstore_adapter_enriches_public_hash_only_entry_from_matching_cached_payload(mock_rekor):
    adapter = SigstoreLogAdapter()
    cached_entry = _make_rekor_entry("evt-1")
    payload_hash = SigstoreLogAdapter._payload_hash_from_entry(cached_entry)
    assert payload_hash is not None
    algorithm, value = payload_hash.split(":", 1)

    public_body = {
        "apiVersion": "0.0.1",
        "kind": "dsse",
        "spec": {
            "signatures": [{"verifier": "cert"}],
            "payloadHash": {"algorithm": algorithm, "value": value},
            "envelopeHash": {"algorithm": algorithm, "value": value},
        },
    }
    mock_rekor.return_value.log.entries.get.return_value = {
        "body": base64.b64encode(json.dumps(public_body).encode("utf-8")).decode("utf-8"),
        "logIndex": 123,
        "integratedTime": 1700000000,
        "logID": "rekor-log-id",
        "verification": {"inclusionProof": {}, "signedEntryTimestamp": "set"},
    }

    SigstoreLogAdapter._bundle_entry_cache[SigstoreLogAdapter._cache_key(adapter.rekor_url, "123")] = cached_entry

    entry = adapter.get_entry("123")

    assert entry["_tc_replay_provenance"] == "cache-assisted"
    assert entry["body"]["spec"]["payload"]
    assert entry["body"]["spec"]["payloadHash"]["value"] == value


def test_sigstore_adapter_enriches_public_hash_only_entry_from_mirror_when_cache_is_empty(mock_rekor):
    adapter = SigstoreLogAdapter()
    cached_entry = _make_rekor_entry("evt-1")
    payload_hash = SigstoreLogAdapter._payload_hash_from_entry(cached_entry)
    assert payload_hash is not None
    algorithm, value = payload_hash.split(":", 1)

    public_body = {
        "apiVersion": "0.0.1",
        "kind": "dsse",
        "spec": {
            "signatures": [{"verifier": "cert"}],
            "payloadHash": {"algorithm": algorithm, "value": value},
            "envelopeHash": {"algorithm": algorithm, "value": value},
        },
    }
    mock_rekor.return_value.log.entries.get.return_value = {
        "body": base64.b64encode(json.dumps(public_body).encode("utf-8")).decode("utf-8"),
        "uuid": "log-id-123",
        "integratedTime": 1700000000,
        "logID": "rekor-log-id",
        "verification": {"inclusionProof": {}, "signedEntryTimestamp": "set"},
    }

    class _Mirror:
        def resolve_bundle(self, requested_payload_hash):
            assert requested_payload_hash == payload_hash
            return {
                "payload_hash": requested_payload_hash,
                "artifact_digest": "sha256:" + ("ab" * 32),
                "annotations": {"payload_b64": cached_entry["body"]["spec"]["payload"]},
            }

    adapter.bundle_mirror = _Mirror()

    entry = adapter.get_entry("log-id-123")

    assert entry["_tc_replay_provenance"] == "mirror"
    assert entry["body"]["spec"]["payload"] == cached_entry["body"]["spec"]["payload"]
    assert entry["body"]["spec"]["payloadHash"]["value"] == value


def test_sigstore_adapter_enriches_public_hash_only_entry_from_attestation_before_fallbacks(mock_rekor):
    adapter = SigstoreLogAdapter()
    statement = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "launch",
            "digest": "sha384:evt-1",
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    payload_bytes = json.dumps(statement).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    mock_rekor.return_value.log.entries.get.return_value = {
        "body": base64.b64encode(
            json.dumps(
                {
                    "apiVersion": "0.0.1",
                    "kind": "intoto",
                    "spec": {
                        "content": {
                            "payloadHash": {"algorithm": "sha256", "value": payload_hash}
                        }
                    },
                }
            ).encode("utf-8")
        ).decode("utf-8"),
        "uuid": "log-id-123",
        "attestation": base64.b64encode(payload_bytes).decode("utf-8"),
    }

    entry = adapter.get_entry("log-id-123")

    assert entry["_tc_replay_provenance"] == "attestation-storage"
    assert entry["body"]["spec"]["payload"] == base64.b64encode(payload_bytes).decode("utf-8")


def test_sigstore_adapter_traverse_prefers_materialized_candidate_for_prev_lookup_hash(mock_rekor):
    adapter = SigstoreLogAdapter()
    predecessor_entry = _make_rekor_entry("evt-1", sequence_num=2)
    predecessor_entry["uuid"] = "materialized-predecessor"
    predecessor_payload_hash = SigstoreLogAdapter._payload_hash_from_entry(predecessor_entry)
    assert predecessor_payload_hash is not None
    algorithm, value = predecessor_payload_hash.split(":", 1)

    public_duplicate = {
        "uuid": "public-duplicate",
        "body": {
            "spec": {
                "payloadHash": {"algorithm": algorithm, "value": value},
                "signatures": [{"verifier": "cert"}],
                "envelopeHash": {"algorithm": algorithm, "value": value},
            }
        },
    }

    head_entry = _make_rekor_entry("evt-2", sequence_num=3, prev_lookup_hash=predecessor_payload_hash)
    head_entry["uuid"] = "head-entry"

    def _get_entry(log_id):
        if log_id == "head-entry":
            return head_entry
        if log_id == "materialized-predecessor":
            return predecessor_entry
        raise AssertionError(f"unexpected log id: {log_id}")

    with patch.object(adapter, "get_entry", side_effect=_get_entry):
        with patch.object(adapter, "find_entries_by_payload_hash", return_value=[public_duplicate, predecessor_entry]):
            traversed = adapter.traverse("head-entry", count=10)

    assert len(traversed) == 2
    assert traversed[0]["uuid"] == "head-entry"
    assert traversed[1]["uuid"] == "materialized-predecessor"


def test_sigstore_adapter_merges_attestation_from_raw_rekor_response(mock_rekor):
    adapter = SigstoreLogAdapter()
    statement = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "launch",
            "digest": "sha384:evt-1",
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    payload_bytes = json.dumps(statement).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    mock_rekor.return_value.log.entries.get.return_value = {
        "body": base64.b64encode(
            json.dumps(
                {
                    "apiVersion": "0.0.1",
                    "kind": "intoto",
                    "spec": {
                        "content": {
                            "payloadHash": {"algorithm": "sha256", "value": payload_hash}
                        }
                    },
                }
            ).encode("utf-8")
        ).decode("utf-8"),
        "uuid": "log-id-raw-123",
    }

    class _Response:
        def read(self):
            return json.dumps(
                {
                    "log-id-raw-123": {
                        "body": mock_rekor.return_value.log.entries.get.return_value["body"],
                        "attestation": {"data": base64.b64encode(payload_bytes).decode("utf-8")},
                    }
                }
            ).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    with patch("tlog.backends.rekor.adapter.urllib.request.urlopen", return_value=_Response()):
        entry = adapter.get_entry("log-id-raw-123")

    assert entry["attestation"]["data"] == base64.b64encode(payload_bytes).decode("utf-8")
    assert entry["_tc_replay_provenance"] == "attestation-storage"
    assert entry["body"]["spec"]["payload"] == base64.b64encode(payload_bytes).decode("utf-8")


def test_sigstore_adapter_retries_raw_rekor_attestation_until_available(mock_rekor):
    adapter = SigstoreLogAdapter()
    statement = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "launch",
            "digest": "sha384:evt-1",
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    payload_bytes = json.dumps(statement).encode("utf-8")
    payload_hash = hashlib.sha256(payload_bytes).hexdigest()
    mock_rekor.return_value.log.entries.get.return_value = {
        "body": base64.b64encode(
            json.dumps(
                {
                    "apiVersion": "0.0.1",
                    "kind": "intoto",
                    "spec": {
                        "content": {
                            "payloadHash": {"algorithm": "sha256", "value": payload_hash},
                            "envelope": {"signatures": [{"sig": "abc"}]},
                        }
                    },
                }
            ).encode("utf-8")
        ).decode("utf-8"),
        "uuid": "log-id-retry-123",
    }

    raw_without_attestation = {
        "log-id-retry-123": {
            "body": mock_rekor.return_value.log.entries.get.return_value["body"],
        }
    }
    raw_with_attestation = {
        "log-id-retry-123": {
            "body": mock_rekor.return_value.log.entries.get.return_value["body"],
            "attestation": {"data": base64.b64encode(payload_bytes).decode("utf-8")},
        }
    }

    with patch.object(adapter, "_fetch_raw_rekor_entry", side_effect=[
        SigstoreLogAdapter._normalize_raw_entry_response(raw_without_attestation),
        SigstoreLogAdapter._normalize_raw_entry_response(raw_with_attestation),
    ]) as fetch_raw, patch("tlog.backends.rekor.adapter.time.sleep") as sleep_mock:
        entry = adapter.get_entry("log-id-retry-123")

    assert fetch_raw.call_count == 2
    sleep_mock.assert_called_once()
    assert entry["_tc_replay_provenance"] == "attestation-storage"
    assert entry["body"]["spec"]["payload"] == base64.b64encode(payload_bytes).decode("utf-8")

def test_sigstore_adapter_traverse(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_instance = mock_rekor.return_value

    # fake body spec payload
    def make_entry(sequence_num, digest, prev_lookup_hash=None):
        payload = {
            "predicate": {
                "chain_id": "default",
                "sequence_num": sequence_num,
                "digest": digest,
                "prev_event_digest": None if sequence_num == 1 else "sha384:evt-1",
                "prev_lookup_hash": prev_lookup_hash,
            }
        }
        enc_payload = base64.b64encode(json.dumps(payload).encode('utf-8')).decode('utf-8')
        return {"uuid": f"id-{sequence_num}", "body": {"spec": {"payload": enc_payload}}}

    entry_1 = make_entry(1, "sha384:evt-1")
    entry_2 = make_entry(2, "sha384:evt-2", adapter._payload_hash_from_entry(entry_1))

    mock_instance.log.entries.get.side_effect = [
        {"id-2": entry_2},
        None
    ]
    mock_instance.log.entries.get.side_effect = [
        {"id-2": entry_2},
    ]

    results = adapter.traverse("id-2", count=5)
    
    # Reservation-backed replay no longer traverses predecessor through cache adjacency.
    assert len(results) == 1


def test_sigstore_adapter_traverse_follows_prev_lookup_hash_candidates(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_instance = mock_rekor.return_value

    def make_entry(sequence_num, digest, prev_lookup_hash=None):
        payload = {
            "predicate": {
                "chain_id": "default",
                "event_type": "chain.init" if sequence_num == 1 else "launch",
                "sequence_num": sequence_num,
                "digest": digest,
                "prev_event_digest": None if sequence_num == 1 else "sha384:evt-1",
                "prev_lookup_hash": prev_lookup_hash,
            }
        }
        enc_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
        return {"uuid": f"id-{sequence_num}", "body": {"spec": {"payload": enc_payload}}}

    entry_1 = make_entry(1, "sha384:evt-1")
    entry_2 = make_entry(2, "sha384:evt-2", adapter._payload_hash_from_entry(entry_1))

    mock_instance.log.entries.get.side_effect = [
        {"id-2": entry_2},
        {"id-1": entry_1},
    ]

    with patch.object(adapter, "find_entries_by_payload_hash", return_value=[entry_1]):
        results = adapter.traverse("id-2", count=5)

    assert [entry["uuid"] for entry in results] == ["id-2", "id-1"]


def test_sigstore_adapter_traverse_keeps_normalized_entry_dict(mock_rekor):
    adapter = SigstoreLogAdapter()
    mock_instance = mock_rekor.return_value

    payload = {"predicate": {"event_id": "evt-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}}
    enc_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    mock_instance.log.entries.get.return_value = {
        "uuid": "id-1",
        "body": {"spec": {"payload": enc_payload}},
    }

    results = adapter.traverse("id-1", count=1)

    assert len(results) == 1
    assert results[0]["uuid"] == "id-1"
    assert isinstance(results[0], dict)


def test_oci_bundle_mirror_round_trip_by_payload_hash(tmp_path):
    mirror = OciBundleMirror(str(tmp_path))
    bundle_json = json.dumps({"bundle": "value", "entries": [1, 2, 3]})
    payload_hash = "sha256:" + hashlib.sha256(b"payload-bytes").hexdigest()

    manifest = mirror.publish_bundle(
        payload_hash=payload_hash,
        bundle_json=bundle_json,
        annotations={"chain_id": "default", "sequence_num": 2},
    )
    resolved = mirror.resolve_bundle(payload_hash)

    assert manifest["payloadHash"] == payload_hash
    assert resolved is not None
    assert resolved["payload_hash"] == payload_hash
    assert resolved["bundle_json"] == bundle_json
    assert resolved["annotations"]["chain_id"] == "default"


def test_oci_bundle_mirror_uses_payload_hash_as_primary_lookup(tmp_path):
    mirror = OciBundleMirror(str(tmp_path))
    payload_hash = "sha256:" + hashlib.sha256(b"payload-a").hexdigest()
    bundle_json = json.dumps({"bundle": "A"})

    mirror.publish_bundle(
        payload_hash=payload_hash,
        bundle_json=bundle_json,
        annotations={"chain_id": "workload-a", "sequence_num": 7},
    )

    resolved = mirror.resolve_bundle(payload_hash)

    assert resolved is not None
    assert resolved["bundle_json"] == bundle_json
    assert mirror.resolve_bundle("sha256:" + hashlib.sha256(b"missing").hexdigest()) is None


def test_oci_bundle_mirror_rejects_malformed_payload_hash(tmp_path):
    mirror = OciBundleMirror(str(tmp_path))

    with pytest.raises(ValueError):
        mirror.publish_bundle(payload_hash="not-a-hash", bundle_json="{}")


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
    def __init__(
        self,
        entries=None,
        error=None,
        candidates=None,
        lookup_error=None,
        require_mirror=False,
        head_log_verification=None,
    ):
        self._entries = entries or []
        self._error = error
        self._candidates = candidates or {}
        self._lookup_error = lookup_error
        self.require_mirror = require_mirror
        self._head_log_verification = head_log_verification or {
            "status": "verified",
            "scope": "accepted-head-only",
            "log_id": None,
            "entry_uuid": None,
            "log_index": None,
            "inclusion_status": "verified",
            "checkpoint_status": "verified",
            "checkpoint_origin": None,
            "bootstrap_trust": {
                "configured": False,
                "source": None,
                "consistency_proven": False,
            },
            "proof": None,
            "reasons": [],
        }

    def submit_bundle(self, bundle, prev_log_id=None):
        raise NotImplementedError()

    def get_entry(self, log_id):
        raise NotImplementedError()

    def traverse(self, end_log_id, count=10):
        if self._error:
            raise self._error
        return self._entries

    def find_entries_by_payload_hash(self, payload_hash):
        if self._lookup_error:
            raise self._lookup_error
        return self._candidates.get(payload_hash, [])

    def verify_head_entry_inclusion(self, log_id, checkpoint_public_key_pem=None):
        result = dict(self._head_log_verification)
        result.setdefault("log_id", log_id)
        return result


_UNSET = object()


def _make_rekor_entry(
    event_id: str,
    event_type: str = "commit",
    *,
    chain_id: str = "default",
    sequence_num: int | None = None,
    digest: str | None = None,
    prev_event_digest: str | object = _UNSET,
    prev_lookup_hash: str | object = _UNSET,
    predicate_entries: list[dict[str, object]] | None = None,
    owner_authorization: dict[str, object] | None = None,
):
    if sequence_num is None:
        sequence_num = 1 if event_id == "evt-1" else 2
    if digest is None:
        digest = f"sha384:{event_id}"
    if prev_event_digest is _UNSET:
        prev_event_digest = None if sequence_num == 1 else "sha384:evt-1"
    if prev_lookup_hash is _UNSET:
        prev_lookup_hash = None
    payload = {
        "subject": [{"name": f"trusted-log-chain_{chain_id}", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": chain_id,
            "sequence_num": sequence_num,
            "event_id": event_id,
            "event_type": event_type,
            "digest": digest,
            "entries": predicate_entries or [],
            "prev_event_digest": prev_event_digest,
            "prev_lookup_hash": prev_lookup_hash,
        },
    }
    if owner_authorization is not None:
        payload["predicate"]["owner_authorization"] = owner_authorization
    enc_payload = base64.b64encode(json.dumps(payload).encode("utf-8")).decode("utf-8")
    return {"body": {"spec": {"payload": enc_payload}}}


def _make_owner_keypair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    private_key = ec.generate_private_key(ec.SECP384R1())
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_key, public_key


def test_verify_record_returns_structured_entry_details():
    first_entry = _make_rekor_entry("evt-1")
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    second_payload["predicate"]["prev_lookup_hash"] = "sha256:" + hashlib.sha256(
        base64.b64decode(first_entry["body"]["spec"]["payload"])
    ).hexdigest()
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[second_entry, first_entry]))

    with patch("tc_api.transparency.verification._extract_signer_identity", side_effect=["alice@example.com", "alice@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["source"] == "immutable_backend"
    assert result.details["entry_count"] == 2
    assert result.details["observed_entry_count"] == 2
    assert result.details["applied_signer_identity"] == "alice@example.com"
    assert len(result.details["entries"]) == 2
    assert result.details["entries"][0]["event_id"] == "evt-2"
    assert result.details["entries"][0]["signer_identity_match"] is True
    assert result.details["head_log_verification"]["status"] == "verified"


def test_sigstore_adapter_verify_head_entry_inclusion_reports_degraded_when_checkpoint_trust_missing(mock_rekor):
    adapter = SigstoreLogAdapter()
    raw_entry = {
        "uuid": "uuid-log-tail",
        "logIndex": 123,
        "verification": {
            "inclusionProof": {
                "logIndex": 123,
                "rootHash": "abcd",
                "treeSize": 1,
                "hashes": [],
                "checkpoint": "rekor.sigstore.dev - 2605736670972794746\n1\nabcd\n",
            },
            "signedEntryTimestamp": "set",
        },
    }

    with patch.object(adapter, "_fetch_raw_rekor_entry", return_value=raw_entry), \
         patch.object(adapter, "_log_entry_from_raw_entry", return_value=MagicMock()), \
         patch("tlog.backends.rekor.adapter.verify_merkle_inclusion") as mock_verify_merkle:
        result = adapter.verify_head_entry_inclusion("log-tail")

    mock_verify_merkle.assert_called_once()
    assert result["status"] == "degraded"
    assert result["inclusion_status"] == "verified"
    assert result["checkpoint_status"] == "unconfigured"
    assert "not configured" in result["reasons"][0]


def test_sigstore_adapter_verify_head_entry_inclusion_reports_failed_checkpoint_validation(mock_rekor):
    adapter = SigstoreLogAdapter()
    raw_entry = {
        "uuid": "uuid-log-tail",
        "logIndex": 123,
        "verification": {
            "inclusionProof": {
                "logIndex": 123,
                "rootHash": "abcd",
                "treeSize": 1,
                "hashes": [],
                "checkpoint": "rekor.sigstore.dev - 2605736670972794746\n1\nabcd\n",
            },
            "signedEntryTimestamp": "set",
        },
    }

    with patch.object(adapter, "_fetch_raw_rekor_entry", return_value=raw_entry), \
         patch.object(adapter, "_log_entry_from_raw_entry", return_value=MagicMock()), \
         patch.object(adapter, "_load_checkpoint_public_key_pem", return_value=("pem", "explicit-policy")), \
         patch.object(adapter, "_rekor_keyring_from_pem", return_value=MagicMock()), \
         patch("tlog.backends.rekor.adapter.verify_merkle_inclusion"), \
         patch("tlog.backends.rekor.adapter.verify_checkpoint", side_effect=RuntimeError("invalid signature")):
        result = adapter.verify_head_entry_inclusion("log-tail")

    assert result["status"] == "failed"
    assert result["checkpoint_status"] == "invalid"
    assert result["bootstrap_trust"]["source"] == "explicit-policy"
    assert "invalid signature" in result["reasons"][0]


def test_verify_record_preserves_degraded_head_log_verification_details():
    first_entry = _make_rekor_entry("evt-1")
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[first_entry],
            head_log_verification={
                "status": "degraded",
                "scope": "accepted-head-only",
                "log_id": "tail-log-id",
                "inclusion_status": "verified",
                "checkpoint_status": "unconfigured",
                "bootstrap_trust": {
                    "configured": False,
                    "source": None,
                    "consistency_proven": False,
                },
                "proof": None,
                "reasons": ["accepted head checkpoint trust source was not configured"],
            },
        )
    )

    result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is True
    assert result.details["head_log_verification"]["status"] == "degraded"
    assert result.details["head_log_verification"]["checkpoint_status"] == "unconfigured"


def test_verify_record_fails_when_head_log_verification_fails():
    first_entry = _make_rekor_entry("evt-1")
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[first_entry],
            head_log_verification={
                "status": "failed",
                "scope": "accepted-head-only",
                "log_id": "tail-log-id",
                "inclusion_status": "verified",
                "checkpoint_status": "invalid",
                "bootstrap_trust": {
                    "configured": True,
                    "source": "explicit-policy",
                    "consistency_proven": False,
                },
                "proof": None,
                "reasons": ["accepted head checkpoint validation failed: invalid signature"],
            },
        )
    )

    result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is False
    assert result.errors == ["Accepted head-entry transparency-log verification failed"]
    assert result.details["head_log_verification"]["checkpoint_status"] == "invalid"


def test_sigstore_payload_hash_lookup_keeps_mirror_candidate_when_public_lookup_succeeds():
    public_entry = _make_rekor_entry("evt-1", sequence_num=1)
    payload_hash = SigstoreLogAdapter._payload_hash_from_entry(public_entry)
    assert payload_hash is not None

    class _Response:
        def read(self):
            return json.dumps(["123"]).encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    class _Mirror:
        def resolve_bundle(self, requested_payload_hash):
            assert requested_payload_hash == payload_hash
            return {
                "payload_hash": requested_payload_hash,
                "bundle_json": json.dumps({"bundle": "value"}),
                "artifact_digest": "sha256:" + ("ab" * 32),
                "annotations": {
                    "payload_b64": public_entry["body"]["spec"]["payload"],
                },
            }

    adapter = SigstoreLogAdapter(bundle_mirror=_Mirror())

    with patch("tlog.backends.rekor.adapter.urllib.request.urlopen", return_value=_Response()):
        with patch.object(adapter, "get_entry", return_value=public_entry):
            candidates = adapter.find_entries_by_payload_hash(payload_hash)

    assert len(candidates) == 2
    assert any(candidate.get("_tc_replay_provenance") == "mirror" for candidate in candidates)
    assert any(candidate.get("body") == public_entry.get("body") for candidate in candidates)


def test_verify_record_rejects_cache_assisted_history_as_public_proof():
    cache_only_entry = _make_rekor_entry("evt-1", sequence_num=1)
    cache_only_entry["_tc_replay_provenance"] = "cache-assisted"
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[cache_only_entry]))

    result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is False
    assert result.errors == ["Signed predecessor continuity verification failed"]
    entry = result.details["entries"][0]
    assert entry["public_history_ok"] is False
    assert entry["public_history_status"] == "cache-assisted"
    assert entry["predecessor_status"] == "unsupported"


def test_verify_record_rejects_unmaterialized_event_log0_baseline():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[{"body": {"spec": {}}}]))

    result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is False
    entry = result.details["entries"][0]
    assert entry["public_history_ok"] is False
    assert entry["public_history_status"] == "unmaterialized"
    assert entry["predecessor_status"] == "unsupported"
    assert entry["predecessor_ok"] is False


def test_verify_record_filters_by_signer_identity():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[_make_rekor_entry("evt-1"), _make_rekor_entry("evt-2")]))

    with patch("tc_api.transparency.verification._extract_signer_identity", side_effect=["alice@example.com", "bob@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entry_count"] == 1
    assert result.details["filtered_out_count"] == 1
    assert result.details["entries"][0]["event_id"] == "evt-1"


def test_verify_record_filters_out_entries_from_other_chains():
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[
                _make_rekor_entry("evt-foreign", chain_id="other"),
                _make_rekor_entry("evt-1", chain_id="default"),
            ]
        )
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", side_effect=["alice@example.com", "alice@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default"})

    assert result.success is True
    assert result.details["entry_count"] == 1
    assert result.details["filtered_out_count"] == 1
    assert result.details["entries"][0]["event_id"] == "evt-1"


def test_verify_record_fails_on_expected_entry_count_mismatch():
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[_make_rekor_entry("evt-1")]))

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
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


def test_verify_record_fails_on_signed_predecessor_mismatch():
    first_entry = _make_rekor_entry("evt-1")
    second_entry = _make_rekor_entry("evt-2")
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[second_entry, first_entry]))

    with patch("tc_api.transparency.verification._extract_signer_identity", side_effect=["alice@example.com", "alice@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.errors == ["Signed predecessor continuity verification failed"]
    assert result.details["entries"][0]["predecessor_status"] == "missing"


def test_verify_record_uses_public_candidate_discovery_when_traverse_stops_early():
    first_entry = _make_rekor_entry("evt-1")
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_entry["body"]["spec"]["payload"])).hexdigest()
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")

    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={lookup_hash: [first_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["predecessor_status"] == "proven"
    assert result.details["entries"][0]["candidate_count"] == 1


def test_verify_record_marks_mirror_materialization_provenance():
    first_entry = _make_rekor_entry("evt-1")
    first_entry["_tc_replay_provenance"] = "mirror"
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_entry["body"]["spec"]["payload"])).hexdigest()
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")

    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={lookup_hash: [first_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["history_materialization_provenance"] == "mirror"


def test_verify_record_materializes_attestation_storage_predecessor():
    owner_private_key, owner_pub_key = _make_owner_keypair()
    predecessor_payload = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "chain.init",
            "digest": "sha384:evt-1",
            "entries": [
                {"key": "baseline_rtmr", "value": "11" * 48},
                {"key": "ccel_digest", "value": "sha384:" + ("22" * 48)},
                {"key": "pub_key", "value": owner_pub_key},
            ],
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    predecessor_bytes = json.dumps(predecessor_payload).encode("utf-8")
    predecessor_hash = hashlib.sha256(predecessor_bytes).hexdigest()
    predecessor_entry = {
        "uuid": "attested-predecessor",
        "body": {
            "spec": {
                "content": {
                    "payloadHash": {"algorithm": "sha256", "value": predecessor_hash}
                }
            }
        },
        "attestation": base64.b64encode(predecessor_bytes).decode("utf-8"),
    }
    second_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        prev_event_digest="sha384:evt-1",
        prev_lookup_hash=f"sha256:{predecessor_hash}",
        owner_authorization=sign_owner_authorization(
            owner_private_key,
            "default",
            2,
            "sha384:evt-1",
            f"sha256:{predecessor_hash}",
            "sha384:evt-2",
        ),
    )
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={f"sha256:{predecessor_hash}": [predecessor_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["predecessor_status"] == "proven"
    assert result.details["entries"][0]["history_materialization_provenance"] == "attestation-storage"


def test_verify_record_rejects_invalid_attestation_material_without_fallback():
    predecessor_payload = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "chain.init",
            "digest": "sha384:evt-1",
            "entries": [
                {"key": "baseline_rtmr", "value": "11" * 48},
                {"key": "ccel_digest", "value": "sha384:" + ("22" * 48)},
                {"key": "pub_key", "value": "pem"},
            ],
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    predecessor_hash = hashlib.sha256(json.dumps(predecessor_payload).encode("utf-8")).hexdigest()
    invalid_predecessor_entry = {
        "uuid": "invalid-attested-predecessor",
        "body": {
            "spec": {
                "content": {
                    "payloadHash": {"algorithm": "sha256", "value": predecessor_hash}
                }
            }
        },
        "attestation": base64.b64encode(b'{"predicate":{"event_id":"tampered"}}').decode("utf-8"),
    }
    second_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        prev_event_digest="sha384:evt-1",
        prev_lookup_hash=f"sha256:{predecessor_hash}",
    )
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={f"sha256:{predecessor_hash}": [invalid_predecessor_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.details["entries"][0]["predecessor_status"] == "decode_failed"
    assert "Attestation payload hash mismatch" in result.details["entries"][0]["errors"]


def test_verify_record_falls_back_to_mirror_when_attestation_material_is_invalid():
    owner_private_key, owner_pub_key = _make_owner_keypair()
    predecessor_payload = {
        "subject": [{"name": "trusted-log-chain_default", "digest": {"sha384": "abc"}}],
        "predicate": {
            "chain_id": "default",
            "sequence_num": 1,
            "event_id": "evt-1",
            "event_type": "chain.init",
            "digest": "sha384:evt-1",
            "entries": [
                {"key": "baseline_rtmr", "value": "11" * 48},
                {"key": "ccel_digest", "value": "sha384:" + ("22" * 48)},
                {"key": "pub_key", "value": owner_pub_key},
            ],
            "prev_event_digest": None,
            "prev_lookup_hash": None,
        },
    }
    predecessor_bytes = json.dumps(predecessor_payload).encode("utf-8")
    predecessor_hash = hashlib.sha256(predecessor_bytes).hexdigest()
    invalid_predecessor_entry = {
        "uuid": "invalid-attested-predecessor",
        "body": {
            "spec": {
                "content": {
                    "payloadHash": {"algorithm": "sha256", "value": predecessor_hash}
                }
            }
        },
        "attestation": base64.b64encode(b'{"predicate":{"event_id":"tampered"}}').decode("utf-8"),
    }
    mirror_entry = {
        "uuid": "mirror-predecessor",
        "body": {"spec": {"payload": base64.b64encode(predecessor_bytes).decode("utf-8")}},
    }
    mirror_entry["_tc_replay_provenance"] = "mirror"
    second_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        prev_event_digest="sha384:evt-1",
        prev_lookup_hash=f"sha256:{predecessor_hash}",
        owner_authorization=sign_owner_authorization(
            owner_private_key,
            "default",
            2,
            "sha384:evt-1",
            f"sha256:{predecessor_hash}",
            "sha384:evt-2",
        ),
    )
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[second_entry],
            candidates={f"sha256:{predecessor_hash}": [invalid_predecessor_entry, mirror_entry]},
        )
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["history_materialization_provenance"] == "mirror"


def test_verify_record_fails_on_invalid_owner_authorization():
    owner_private_key, owner_pub_key = _make_owner_keypair()
    wrong_private_key, _ = _make_owner_keypair()
    first_entry = _make_rekor_entry(
        "evt-1",
        event_type="chain.init",
        sequence_num=1,
        digest="sha384:evt-1",
        predicate_entries=[
            {"key": "baseline_rtmr", "value": "11" * 48},
            {"key": "ccel_digest", "value": "sha384:" + ("22" * 48)},
            {"key": "pub_key", "value": owner_pub_key},
        ],
    )
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_entry["body"]["spec"]["payload"])).hexdigest()
    second_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        digest="sha384:evt-2",
        prev_event_digest="sha384:evt-1",
        prev_lookup_hash=lookup_hash,
        owner_authorization=sign_owner_authorization(
            wrong_private_key,
            "default",
            2,
            "sha384:evt-1",
            lookup_hash,
            "sha384:evt-2",
        ),
    )
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[second_entry, first_entry]))

    with patch("tc_api.transparency.verification._extract_signer_identity", side_effect=["alice@example.com", "alice@example.com"]):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.errors == ["Owner authorization verification failed"]
    assert result.details["entries"][0]["owner_ok"] is False
    assert result.details["entries"][0]["owner_status"] == "invalid"


def test_verify_record_requires_mirror_when_policy_demands_it():
    first_entry = _make_rekor_entry("evt-1")
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_entry["body"]["spec"]["payload"])).hexdigest()
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")

    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={lookup_hash: [first_entry]}, require_mirror=True)
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record(
            "tail-log-id",
            policy={"chain_id": "default", "signer_identity": "alice@example.com", "require_mirror": True},
        )

    assert result.success is False
    assert result.details["entries"][0]["predecessor_status"] == "unsupported"
    assert "Mirror-required policy" in result.details["entries"][0]["errors"][0]


def test_verify_record_reports_decode_failed_when_candidates_cannot_be_normalized():
    first_entry = {"uuid": "broken-candidate", "body": {"spec": {"payload": "not-base64"}}}
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    second_payload["predicate"]["prev_lookup_hash"] = "sha256:broken"
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={"sha256:broken": [first_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.details["entries"][0]["predecessor_status"] == "decode_failed"
    assert result.details["entries"][0]["candidate_count"] == 1
    assert result.details["entries"][0]["materialized_candidate_count"] == 0


def test_verify_record_prefers_materialized_candidate_over_public_duplicate_with_same_identity():
    first_entry = _make_rekor_entry("evt-1")
    first_entry["uuid"] = "shared-predecessor"
    first_payload_b64 = first_entry["body"]["spec"]["payload"]
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_payload_b64)).hexdigest()

    public_duplicate = {
        "uuid": "shared-predecessor",
        "body": {
            "spec": {
                "payloadHash": {
                    "algorithm": "sha256",
                    "value": lookup_hash.split(":", 1)[1],
                }
            }
        },
    }
    materialized_duplicate = json.loads(json.dumps(first_entry))
    materialized_duplicate["uuid"] = "shared-predecessor"
    materialized_duplicate["attestation"] = {"payload": first_payload_b64}
    materialized_duplicate["_tc_replay_provenance"] = "attestation-storage"

    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")

    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[second_entry],
            candidates={lookup_hash: [public_duplicate, materialized_duplicate]},
        )
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["predecessor_status"] == "proven"
    assert result.details["entries"][0]["candidate_count"] == 1
    assert result.details["entries"][0]["materialized_candidate_count"] == 1


def test_verify_record_reports_ambiguous_when_multiple_candidates_match():
    first_entry = _make_rekor_entry("evt-1")
    duplicate_entry = _make_rekor_entry("evt-1")
    duplicate_entry["uuid"] = "dup-evt-1"
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(first_entry["body"]["spec"]["payload"])).hexdigest()
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(entries=[second_entry], candidates={lookup_hash: [first_entry, duplicate_entry]})
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.details["entries"][0]["predecessor_status"] == "ambiguous"
    assert result.details["entries"][0]["matched_candidate_count"] == 2


def test_verify_record_prefers_mirror_when_public_and_mirror_match_same_predecessor():
    public_entry = _make_rekor_entry("evt-1")
    public_entry["uuid"] = "public-evt-1"
    mirror_entry = json.loads(json.dumps(public_entry))
    mirror_entry["uuid"] = "mirror-evt-1"
    mirror_entry["_tc_replay_provenance"] = "mirror"
    second_entry = _make_rekor_entry("evt-2")
    second_payload = json.loads(base64.b64decode(second_entry["body"]["spec"]["payload"]).decode("utf-8"))
    lookup_hash = "sha256:" + hashlib.sha256(base64.b64decode(public_entry["body"]["spec"]["payload"])).hexdigest()
    second_payload["predicate"]["prev_lookup_hash"] = lookup_hash
    second_entry["body"]["spec"]["payload"] = base64.b64encode(json.dumps(second_payload).encode("utf-8")).decode("utf-8")
    api = TrustedLogAPI(
        immutable_log=StubImmutableLog(
            entries=[second_entry],
            candidates={lookup_hash: [public_entry, mirror_entry]},
            require_mirror=True,
        )
    )

    with patch("tc_api.transparency.verification._extract_signer_identity", return_value="alice@example.com"):
        result = api.verify_record(
            "tail-log-id",
            policy={"chain_id": "default", "signer_identity": "alice@example.com", "require_mirror": True},
        )

    assert result.success is True
    assert result.details["entries"][0]["predecessor_status"] == "proven"
    assert result.details["entries"][0]["matched_candidate_count"] == 2
    assert result.details["entries"][0]["history_materialization_provenance"] == "mirror"


def test_verify_record_reports_degraded_boundary_for_legacy_to_reservation_transition():
    origin_entry = _make_rekor_entry(
        "evt-1",
        sequence_num=1,
        prev_event_digest=None,
        prev_lookup_hash=None,
    )
    legacy_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        prev_event_digest=None,
        prev_lookup_hash=None,
    )
    legacy_lookup_hash = "sha256:" + hashlib.sha256(
        base64.b64decode(legacy_entry["body"]["spec"]["payload"])
    ).hexdigest()
    signed_entry = _make_rekor_entry(
        "evt-3",
        sequence_num=3,
        prev_event_digest="sha384:evt-2",
        prev_lookup_hash=legacy_lookup_hash,
    )
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[signed_entry, legacy_entry, origin_entry]))

    with patch(
        "tc_api.transparency.verification._extract_signer_identity",
        side_effect=["alice@example.com", "alice@example.com", "alice@example.com"],
    ):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is True
    assert result.details["entries"][0]["predecessor_status"] == "proven"
    assert result.details["entries"][1]["predecessor_status"] == "unverifiable"
    assert result.details["entries"][1]["boundary_status"] == "degraded"


def test_verify_record_reports_invalid_boundary_for_reservation_to_legacy_regression():
    origin_entry = _make_rekor_entry(
        "evt-1",
        sequence_num=1,
        prev_event_digest=None,
        prev_lookup_hash=None,
    )
    origin_lookup_hash = "sha256:" + hashlib.sha256(
        base64.b64decode(origin_entry["body"]["spec"]["payload"])
    ).hexdigest()
    signed_entry = _make_rekor_entry(
        "evt-2",
        sequence_num=2,
        prev_event_digest="sha384:evt-1",
        prev_lookup_hash=origin_lookup_hash,
    )
    regressed_entry = _make_rekor_entry(
        "evt-3",
        sequence_num=3,
        prev_event_digest=None,
        prev_lookup_hash=None,
    )
    api = TrustedLogAPI(immutable_log=StubImmutableLog(entries=[regressed_entry, signed_entry, origin_entry]))

    with patch(
        "tc_api.transparency.verification._extract_signer_identity",
        side_effect=["alice@example.com", "alice@example.com", "alice@example.com"],
    ):
        result = api.verify_record("tail-log-id", policy={"chain_id": "default", "signer_identity": "alice@example.com"})

    assert result.success is False
    assert result.errors == ["Signed predecessor continuity verification failed"]
    assert result.details["entries"][0]["predecessor_status"] == "unverifiable"
    assert result.details["entries"][0]["boundary_status"] == "invalid"

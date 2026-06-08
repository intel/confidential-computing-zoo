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

"""Tests for owner-key DSSE signing and intoto entry construction."""
import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.identity.sigstore_baseline import sign_dsse_with_owner_key


@pytest.fixture()
def owner_key_pair():
    private_key = ec.generate_private_key(ec.SECP384R1())
    public_key = private_key.public_key()
    pub_pem = public_key.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_key, public_key, pub_pem


@pytest.fixture()
def sample_statement():
    return json.dumps({
        "_type": "https://in-toto.io/Statement/v0.1",
        "subject": [{"name": "test-chain", "digest": {"sha384": "a" * 96}}],
        "predicateType": "https://trusted-log.dev/v1",
        "predicate": {"event_id": "evt-test-1", "event_type": "test.op"},
    })


# ---- DSSE PAE + signing ----

class TestSignDsseWithOwnerKey:
    def test_returns_valid_envelope_structure(self, owner_key_pair, sample_statement):
        private_key, _, _ = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        assert envelope["payloadType"] == "application/vnd.in-toto+json"
        assert isinstance(envelope["payload"], str)
        assert isinstance(envelope["signatures"], list)
        assert len(envelope["signatures"]) == 1
        assert "sig" in envelope["signatures"][0]

    def test_payload_roundtrips(self, owner_key_pair, sample_statement):
        private_key, _, _ = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        decoded = base64.b64decode(envelope["payload"]).decode("utf-8")
        assert decoded == sample_statement

    def test_signature_verifies(self, owner_key_pair, sample_statement):
        private_key, public_key, _ = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        payload_type = envelope["payloadType"]
        statement_bytes = sample_statement.encode("utf-8")
        pae = (
            f"DSSEv1 {len(payload_type)} {payload_type} "
            f"{len(statement_bytes)} {sample_statement}"
        ).encode("utf-8")

        sig_der = base64.b64decode(envelope["signatures"][0]["sig"])
        public_key.verify(sig_der, pae, ec.ECDSA(hashes.SHA256()))

    def test_sha256_not_sha384(self, owner_key_pair, sample_statement):
        """Verify the signing uses SHA-256 (Rekor requirement), not SHA-384."""
        private_key, public_key, _ = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        payload_type = envelope["payloadType"]
        statement_bytes = sample_statement.encode("utf-8")
        pae = (
            f"DSSEv1 {len(payload_type)} {payload_type} "
            f"{len(statement_bytes)} {sample_statement}"
        ).encode("utf-8")

        sig_der = base64.b64decode(envelope["signatures"][0]["sig"])

        # SHA-256 verification should pass
        public_key.verify(sig_der, pae, ec.ECDSA(hashes.SHA256()))

        # SHA-384 verification should fail
        with pytest.raises(Exception):
            public_key.verify(sig_der, pae, ec.ECDSA(hashes.SHA384()))


# ---- intoto entry construction ----

class TestBuildIntotoEntryFromOwnerKey:
    def test_entry_structure(self, owner_key_pair, sample_statement):
        from tlog.backends.rekor.adapter import SigstoreLogAdapter

        private_key, _, pub_pem = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        entry = SigstoreLogAdapter.build_intoto_entry_from_owner_key(envelope, pub_pem)
        payload = entry.model_dump(mode="json", by_alias=True)

        assert payload["kind"] == "intoto"
        assert payload["apiVersion"] == "0.0.2"
        spec = payload["spec"]
        content = spec["content"]
        assert "envelope" in content
        assert "hash" in content
        assert content["hash"]["algorithm"] == "sha256"

    def test_public_key_embedded(self, owner_key_pair, sample_statement):
        from tlog.backends.rekor.adapter import SigstoreLogAdapter

        private_key, _, pub_pem = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        entry = SigstoreLogAdapter.build_intoto_entry_from_owner_key(envelope, pub_pem)
        payload = entry.model_dump(mode="json", by_alias=True)

        sigs = payload["spec"]["content"]["envelope"]["signatures"]
        assert len(sigs) == 1
        decoded_pk = base64.b64decode(sigs[0]["publicKey"]).decode()
        assert decoded_pk == pub_pem

    def test_double_base64_payload(self, owner_key_pair, sample_statement):
        from tlog.backends.rekor.adapter import SigstoreLogAdapter

        private_key, _, pub_pem = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        entry = SigstoreLogAdapter.build_intoto_entry_from_owner_key(envelope, pub_pem)
        payload_dump = entry.model_dump(mode="json", by_alias=True)

        intoto_payload = payload_dump["spec"]["content"]["envelope"]["payload"]
        # First decode: get base64 of the statement
        first = base64.b64decode(intoto_payload).decode()
        # Second decode: get original statement
        second = base64.b64decode(first).decode()
        assert second == sample_statement

    def test_envelope_hash_matches(self, owner_key_pair, sample_statement):
        from tlog.backends.rekor.adapter import SigstoreLogAdapter

        private_key, _, pub_pem = owner_key_pair
        envelope = sign_dsse_with_owner_key(sample_statement, private_key)

        entry = SigstoreLogAdapter.build_intoto_entry_from_owner_key(envelope, pub_pem)
        payload_dump = entry.model_dump(mode="json", by_alias=True)

        expected_hash = hashlib.sha256(json.dumps(envelope).encode()).hexdigest()
        assert payload_dump["spec"]["content"]["hash"]["value"] == expected_hash

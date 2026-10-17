#!/usr/bin/env python3
# Copyright (c) 2026 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Trustee-owned verifier. Input is supplied only after TDX/REPORTDATA verification.

No client log bodies, local TruCon cache, URLs or verification booleans are accepted.
The intoto payload must be available from the configured Rekor attestation storage.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import urllib.request
from urllib.parse import urlsplit

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sigstore._internal.rekor.checkpoint import SignedCheckpoint
from sigstore._internal.rekor.client import RekorClient
from sigstore._internal.trust import Keyring, TrustedRoot
from sigstore.models import LogEntry, VerificationMaterial
from sigstore.verify import Verifier
from sigstore.verify.policy import Identity
from sigstore_protobuf_specs.dev.sigstore.common.v1 import PublicKey, PublicKeyDetails
from sigstore_protobuf_specs.dev.sigstore.bundle.v1 import VerificationMaterial as RawVerificationMaterial
from tlog.digest import canonical_json, compute_entry_digest, compute_event_digest
from tlog.backends.rekor.adapter import parse_log_reference

UUID = re.compile(r"(?:[0-9a-f]{64}|[0-9a-f]{80})\Z")
REFERENCE = re.compile(r"(?:[0-9]{1,63}|[0-9a-f]{64}|[0-9a-f]{80})\Z")
RTMR = re.compile(r"[0-9a-f]{96}\Z")
CONTAINER_ID = re.compile(r"[0-9a-f]{64}\Z")
AUTH_FIELDS = ["chain_id", "sequence_num", "prev_event_digest", "prev_lookup_hash", "event_digest"]
MAX_ENTRY_BYTES = 4 * 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    def invalid(value):
        raise ValueError("non-finite JSON number: " + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def b64(value):
    require(isinstance(value, str), "missing base64 material")
    return base64.b64decode(value, validate=True)


def public_key(pem):
    return serialization.load_pem_public_key(pem)


def key_bytes(key):
    return key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)


def p384(key):
    require(isinstance(key, ec.EllipticCurvePublicKey) and isinstance(key.curve, ec.SECP384R1),
            "chain owner must use P-384")
    return key


def rekor_keyring(pem):
    key = public_key(pem)
    require(isinstance(key, ec.EllipticCurvePublicKey), "Rekor checkpoint key must be EC")
    details = {"secp256r1": PublicKeyDetails.PKIX_ECDSA_P256_SHA_256,
               "secp384r1": PublicKeyDetails.PKIX_ECDSA_P384_SHA_384,
               "secp521r1": PublicKeyDetails.PKIX_ECDSA_P521_SHA_512}
    require(key.curve.name in details, "unsupported Rekor curve")
    return Keyring([PublicKey(raw_bytes=key_bytes(key), key_details=details[key.curve.name])])


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Rekor redirect is not allowed")


@dataclass(frozen=True)
class IntotoSigningMaterial:
    """Certificate-verification input for the pinned Sigstore implementation.

    Bundle.from_parts rejects intoto. The common certificate verifier only
    needs these fields: retain the ORIGINAL LogEntry and its signed time,
    without converting the leaf to another Rekor kind or inventing a bundle.
    Payload/DSSE consistency is checked separately in entry().
    """
    signing_certificate: x509.Certificate
    signature: bytes
    log_entry: LogEntry

    @property
    def verification_material(self):
        # intoto supplies a Rekor SET, not an RFC3161 timestamp bundle.
        return VerificationMaterial(RawVerificationMaterial())


class LogVerifier:
    def __init__(self, config):
        self.config = config
        url = urlsplit(config["rekor_url"])
        require(url.scheme == "https" and url.hostname and not url.username and not url.password
                and not url.query and not url.fragment and url.path in ("", "/"), "invalid configured Rekor URL")
        self.url = config["rekor_url"].rstrip("/")
        proxy = config.get("https_proxy")
        proxies = {}
        if proxy is not None:
            proxy_url = urlsplit(proxy)
            require(proxy_url.scheme == "http" and proxy_url.hostname and proxy_url.port
                    and not proxy_url.username and not proxy_url.password
                    and not proxy_url.query and not proxy_url.fragment and proxy_url.path in ("", "/"),
                    "invalid configured HTTPS proxy")
            proxies["https"] = proxy
        self.keyring = rekor_keyring(Path(config["rekor_public_key_path"]).read_bytes())
        baselines = config["allowed_baseline_rtmr"]
        require(isinstance(baselines, list) and baselines and all(isinstance(x, str) and RTMR.fullmatch(x) for x in baselines),
                "approved RTMR2 baselines are required")
        self.init_keys = [key_bytes(public_key(Path(p).read_bytes())) for p in config.get("init_public_key_paths", [])]
        self.sigstore = None
        if config.get("sigstore_trusted_root_path"):
            require(config.get("signer_identity") and config.get("signer_issuer"), "pin the initialization signer identity and issuer")
            self.sigstore = Verifier(rekor=RekorClient(self.url), trusted_root=TrustedRoot.from_file(config["sigstore_trusted_root_path"]))
        require(self.init_keys or self.sigstore, "initialization signer trust is not configured")
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler(proxies), NoRedirect())
        self.deadline = time.monotonic() + 45


    def fetch(self, reference):
        require(isinstance(reference, str) and REFERENCE.fullmatch(reference), "invalid Rekor reference")
        lookup = parse_log_reference(reference)
        suffix = "?logIndex=" + str(lookup["log_index"]) if "log_index" in lookup else "/" + reference
        remaining = self.deadline - time.monotonic()
        require(remaining > 0, "Rekor verification deadline exceeded")
        request = urllib.request.Request(self.url + "/api/v1/log/entries" + suffix, headers={"Accept": "application/json"})
        with self.opener.open(request, timeout=min(5, remaining)) as response:
            require(response.status == 200, "Rekor entry unavailable")
            body = response.read(MAX_ENTRY_BYTES + 1)
        require(len(body) <= MAX_ENTRY_BYTES, "Rekor entry exceeds size limit")
        result = strict_json(body)
        require(isinstance(result, dict) and len(result) == 1, "Rekor must return exactly one entry")
        uuid, raw = next(iter(result.items()))
        require(UUID.fullmatch(uuid) and isinstance(raw, dict), "invalid Rekor entry response")
        if "log_index" in lookup:
            # The global index is authenticated by the SET in entry(), not by
            # comparing it with the shard-local Merkle proof index.
            require(type(raw.get("logIndex")) is int and raw["logIndex"] == lookup["log_index"],
                    "Rekor returned a different log index")
        else:
            require(uuid == reference, "Rekor returned a different UUID")
        return uuid, raw

    def entry(self, reference, owner):
        uuid, raw = self.fetch(reference)
        # A pinned Rekor checkpoint authenticates log inclusion. The DSSE
        # signature below separately authenticates the recorded event payload.
        # Verify the original body, before materializing the detached payload.
        entry = LogEntry._from_response({uuid: raw})
        require(uuid[-64:] == hashlib.sha256(b"\x00" + b64(raw["body"])).hexdigest(), "UUID does not identify this leaf")
        proof = raw["verification"]["inclusionProof"]
        # Merkle proofs use a tree-local index; the SET signs Rekor's global
        # virtual index. They differ after sharding and must be verified in
        # their own signed structures rather than compared for equality.
        signed_checkpoint = SignedCheckpoint.from_text(proof["checkpoint"])
        require(signed_checkpoint.signed_note.signatures, "unsigned Rekor checkpoint")
        checkpoint = signed_checkpoint.checkpoint
        require(checkpoint.log_size == proof["treeSize"], "checkpoint size mismatch")
        # Authenticate integratedTime too (used by Fulcio certificate validation).
        require(raw["verification"].get("signedEntryTimestamp"), "missing Rekor signed entry timestamp")
        entry._verify(self.keyring)
        body = strict_json(b64(raw["body"]))
        require(body.get("kind") == "intoto" and body.get("apiVersion") == "0.0.2", "Rekor intoto entry with stored payload is required")
        content = body["spec"]["content"]
        envelope = content["envelope"]
        require(envelope["payloadType"] == "application/vnd.in-toto+json", "unexpected DSSE payload type")
        attestation = raw.get("attestation")
        payload = b64(attestation.get("data") if isinstance(attestation, dict) else attestation)
        require(content["payloadHash"] == {"algorithm": "sha256", "value": hashlib.sha256(payload).hexdigest()}, "stored payload hash mismatch")
        signatures = envelope["signatures"]
        require(isinstance(signatures, list) and len(signatures) == 1, "exactly one recorder signature is required")
        sig = b64(b64(signatures[0]["sig"]).decode("ascii"))  # intoto serializes []byte containing DSSE base64
        pem = b64(signatures[0]["publicKey"])
        if b"-----BEGIN CERTIFICATE-----" in pem:
            require(self.sigstore is not None, "Fulcio trust is not configured")
            cert = x509.load_pem_x509_certificate(pem)
            # Sigstore's public verify_dsse accepts only Rekor kind=dsse. For
            # intoto use its certificate/CT/time verifier, then explicitly check
            # the committed payload, signature and signer here (steps 7 and 8).
            self.sigstore._verify_common_signing_cert(IntotoSigningMaterial(cert, sig, entry),
                Identity(identity=self.config["signer_identity"], issuer=self.config["signer_issuer"]))
            key = cert.public_key()
        else:
            key = p384(public_key(pem))
            if owner is None:
                require(key_bytes(key) in self.init_keys, "unapproved initialization signer")
            else:
                require(key_bytes(key) == key_bytes(owner), "signer is not the initialized chain owner")
        require(isinstance(key, ec.EllipticCurvePublicKey), "unsupported DSSE signing key")
        payload_type = envelope["payloadType"].encode("utf-8")
        pae = b"DSSEv1 %d %s %d " % (len(payload_type), payload_type, len(payload)) + payload
        key.verify(sig, pae, ec.ECDSA(hashes.SHA256()))
        statement = strict_json(payload)
        require(statement.get("_type") in ("https://in-toto.io/Statement/v0.1", "https://in-toto.io/Statement/v1")
                and statement.get("predicateType") == "https://trusted-log.dev/v1", "unexpected trusted-log statement")
        predicate = statement["predicate"]
        entries = predicate["entries"]
        require(isinstance(entries, list) and all(isinstance(e, dict) and set(e) == {"key", "value"} and isinstance(e["key"], str) for e in entries), "invalid event entries")
        digests = [compute_entry_digest(e["key"], e["value"]) for e in entries]
        require(predicate["entry_digests"] == digests, "entry digest mismatch")
        digest = compute_event_digest(predicate["event_id"], predicate["event_type"], predicate["created"], digests)
        require(predicate["digest"] == digest, "event digest mismatch")
        require(statement["subject"] == [{"name": "trusted-log-chain_" + predicate["chain_id"], "digest": {"sha384": digest[7:]}}], "statement subject mismatch")
        return predicate, "sha256:" + hashlib.sha256(payload).hexdigest(), uuid


    def verify(self, request):
        require(set(request) == {"rekor_entry_ids", "runtime_data", "rtmr2"}, "unexpected verifier input")
        refs, runtime, quoted = request["rekor_entry_ids"], request["runtime_data"], request["rtmr2"]
        require(isinstance(refs, list) and 2 <= len(refs) <= 4096 and all(isinstance(x, str) and REFERENCE.fullmatch(x) for x in refs), "invalid Rekor reference list")
        require(len(set(refs)) == len(refs), "duplicate Rekor reference")
        require(isinstance(quoted, str) and RTMR.fullmatch(quoted), "invalid authenticated RTMR2")
        require(isinstance(runtime, dict) and runtime.get("protocol") == "argus.workload.tdx", "bound workload runtime_data is required")
        fields = ("workload_id", "launch_id", "container_id", "image_config_digest")
        require(all(isinstance(runtime.get(k), str) and runtime[k] for k in fields), "missing current instance fields")
        owner, previous_digest, previous_lookup, current, baseline = None, None, None, None, None
        matched = []
        resolved = set()
        # Verify the complete ordered prefix from initialization, including
        # entries that do not extend RTMR2. A matching launch alone is insufficient.
        for sequence, reference in enumerate(refs, 1):
            p, lookup, uuid = self.entry(reference, owner)
            require(uuid not in resolved, "duplicate resolved Rekor entry")
            resolved.add(uuid)
            require(p["chain_id"] == "default" and type(p["sequence_num"]) is int and p["sequence_num"] == sequence, "chain or sequence mismatch")
            require(p["prev_event_digest"] == previous_digest and p["prev_lookup_hash"] == previous_lookup, "broken signed predecessor link")
            values = {}
            for e in p["entries"]:
                # Repeated operational log entries are legal, but fields used
                # for admission and extend decisions must never be ambiguous.
                if e["key"] in {"baseline_rtmr", "pub_key", "operation_type", "operation_result", "launch_result", "container_info", "container_id", "instance_id"}:
                    require(e["key"] not in values, "ambiguous admission field")
                    values[e["key"]] = e["value"]
            if sequence == 1:
                # Bootstrap the chain owner only from an approved initialization
                # signer and baseline; later events must carry owner authorization.
                require(p["event_type"] == "chain.init", "history must start with initialization")
                baseline = values["baseline_rtmr"]
                require(baseline in self.config["allowed_baseline_rtmr"], "unapproved boot RTMR2 baseline")
                current = bytes.fromhex(baseline)
                owner = p384(public_key(values["pub_key"].encode("utf-8")))
            else:
                require(p["event_type"] != "chain.init", "unexpected reinitialization")
                authorization = p["owner_authorization"]
                require(authorization["algorithm"] == "ecdsa-p384-sha384" and authorization["signed_fields"] == AUTH_FIELDS, "invalid owner authorization format")
                auth_values = [p["chain_id"], sequence, previous_digest, previous_lookup, p["digest"]]
                message = canonical_json(list(map(list, zip(AUTH_FIELDS, auth_values)))).encode("utf-8")
                owner.verify(b64(authorization["signature"]), message, ec.ECDSA(hashes.SHA384()))
                # Match TruCon's extend rules: build events preserve RTMR2, but
                # remain in the signed predecessor chain and must be verified.
                build = p["event_type"] == "build" or p["event_type"].endswith("_build") or values.get("operation_type") == "build"
                if not build:
                    current = hashlib.sha384(current + bytes.fromhex(p["digest"][7:])).digest()
                if matched and values.get("operation_type") in {"stop", "rm"} and values.get("operation_result") == "success":
                    # A successful launch does not remain admissible after a
                    # later confirmed stop/removal of that exact container.
                    container = values.get("container_id")
                    require(isinstance(container, str) and CONTAINER_ID.fullmatch(container),
                            "successful stop/removal must identify a full container ID")
                    require(values.get("instance_id", container) == container,
                            "conflicting stop/removal instance identity")
                    require(container != runtime["container_id"],
                            "target launch was followed by a successful stop/removal")
                info = values.get("container_info")
                if isinstance(info, dict) and (info.get("workload_id"), info.get("launch_id")) == (runtime["workload_id"], runtime["launch_id"]):
                    require(not build and values.get("launch_result") == "success" and info.get("container_Status") == "running", "target has no explicit successful measured launch")
                    require(info.get("container_ID") == runtime["container_id"] and info.get("runtime_image_config_digest") == runtime["image_config_digest"], "launch record does not match current container/image")
                    matched.append(uuid)
            previous_digest, previous_lookup = p["digest"], lookup
        # Only the TDX-authenticated register value closes the history check;
        # the local recorder's cache or a claimed head cannot establish this.
        require(current.hex() == quoted, "history does not reproduce Quote RTMR2")
        require(len(matched) == 1, "exactly one target launch record is required")
        return {"verified": True, "baseline_rtmr": baseline, "launch_entry_uuid": matched[0]}








def main():
    try:
        require(len(sys.argv) == 2, "usage: verify_trucon.py <server-owned-config.json>")
        raw = sys.stdin.buffer.read(524289)
        require(len(raw) <= 524288, "verifier request exceeds size limit")
        request = strict_json(raw)
        verifier = LogVerifier(strict_json(Path(sys.argv[1]).read_bytes()))
        verdict = verifier.verify(request)
        print(json.dumps(verdict, separators=(",", ":")))
    except Exception as exc:
        print("TruCon verification failed: " + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

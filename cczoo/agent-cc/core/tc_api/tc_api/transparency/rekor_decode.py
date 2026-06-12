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

import hashlib
import json
import logging
from typing import Any, Dict, Optional

from cryptography import x509
from cryptography.x509.oid import NameOID

from tlog.digest import canonical_json


logger = logging.getLogger(__name__)


def _decode_rekor_body(entry: Dict[str, Any]) -> Dict[str, Any]:
    body = entry.get("body", {})
    if isinstance(body, dict):
        return body
    if isinstance(body, str):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            try:
                import base64

                return json.loads(base64.b64decode(body).decode("utf-8"))
            except Exception:
                return {}
    return {}


def _decode_dsse_payload(body: Dict[str, Any]) -> Dict[str, Any]:
    spec = body.get("spec", {})

    payload = spec.get("payload")
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            import base64

            return json.loads(base64.b64decode(payload).decode("utf-8"))
        except Exception:
            return {}

    proposed_content = spec.get("proposedContent", {})
    if isinstance(proposed_content, dict):
        envelope = proposed_content.get("envelope")
        if isinstance(envelope, str):
            try:
                envelope_json = json.loads(envelope)
                envelope_payload = envelope_json.get("payload")
                if isinstance(envelope_payload, str):
                    import base64

                    return json.loads(base64.b64decode(envelope_payload).decode("utf-8"))
            except Exception:
                return {}

    content = spec.get("content", {})
    if isinstance(content, dict):
        envelope = content.get("envelope")
        if isinstance(envelope, dict):
            envelope_payload = envelope.get("payload")
            if isinstance(envelope_payload, str):
                try:
                    import base64

                    return json.loads(base64.b64decode(envelope_payload).decode("utf-8"))
                except Exception:
                    return {}
    return {}


def _extract_committed_payload_hash(body: Dict[str, Any]) -> Optional[str]:
    spec = body.get("spec", {}) if isinstance(body, dict) else {}
    if not isinstance(spec, dict):
        return None

    for payload_hash in (
        spec.get("payloadHash"),
        (spec.get("content") or {}).get("payloadHash") if isinstance(spec.get("content"), dict) else None,
    ):
        if isinstance(payload_hash, dict):
            algorithm = payload_hash.get("algorithm")
            value = payload_hash.get("value")
            if isinstance(algorithm, str) and isinstance(value, str):
                return f"{algorithm}:{value}"

    encoded_payload = spec.get("payload")
    if not isinstance(encoded_payload, str):
        content = spec.get("content")
        if isinstance(content, dict):
            envelope = content.get("envelope")
            if isinstance(envelope, dict):
                encoded_payload = envelope.get("payload")
    if not isinstance(encoded_payload, str):
        return None
    try:
        import base64

        return "sha256:" + hashlib.sha256(base64.b64decode(encoded_payload)).hexdigest()
    except Exception:
        return None


def _decode_attestation_payload(entry: Dict[str, Any], expected_payload_hash: Optional[str]) -> tuple[Dict[str, Any], Optional[str]]:
    attestation = entry.get("attestation")
    if attestation is None:
        return {}, None

    attestation_bytes: Optional[bytes] = None
    if isinstance(attestation, dict):
        for key in ("payload", "data"):
            value = attestation.get(key)
            if isinstance(value, str):
                try:
                    import base64

                    attestation_bytes = base64.b64decode(value)
                except Exception:
                    attestation_bytes = value.encode("utf-8")
                break
        if attestation_bytes is None:
            envelope = attestation.get("envelope")
            if isinstance(envelope, dict) and isinstance(envelope.get("payload"), str):
                try:
                    import base64

                    attestation_bytes = base64.b64decode(envelope["payload"])
                except Exception:
                    attestation_bytes = envelope["payload"].encode("utf-8")
        if attestation_bytes is None:
            try:
                attestation_bytes = canonical_json(attestation).encode("utf-8")
            except Exception:
                return {}, "Attestation payload could not be decoded"
    elif isinstance(attestation, str):
        try:
            import base64

            attestation_bytes = base64.b64decode(attestation)
        except Exception:
            attestation_bytes = attestation.encode("utf-8")
    else:
        return {}, "Attestation payload could not be decoded"

    if not attestation_bytes:
        return {}, "Attestation payload could not be decoded"

    observed_hash = "sha256:" + hashlib.sha256(attestation_bytes).hexdigest()
    if expected_payload_hash and observed_hash != expected_payload_hash:
        return {}, "Attestation payload hash mismatch"

    try:
        return json.loads(attestation_bytes.decode("utf-8")), None
    except Exception:
        return {}, "Attestation payload could not be decoded"


def _extract_signer_identity(entry: dict) -> Optional[str]:
    try:
        import base64

        body = entry.get("body", {})
        if isinstance(body, str):
            body = json.loads(base64.b64decode(body).decode("utf-8"))

        spec = body.get("spec", {})
        cert_b64_candidates = []

        signatures = spec.get("signatures", []) or []
        for signature in signatures:
            if not isinstance(signature, dict):
                continue
            verifier = signature.get("verifier")
            if verifier:
                cert_b64_candidates.append(verifier)
            public_key = signature.get("publicKey")
            if isinstance(public_key, dict):
                content = public_key.get("content")
                if content:
                    cert_b64_candidates.append(content)
            elif public_key:
                cert_b64_candidates.append(public_key)

        proposed_content = spec.get("proposedContent", {})
        if isinstance(proposed_content, dict):
            verifiers = proposed_content.get("verifiers", []) or []
            cert_b64_candidates.extend(v for v in verifiers if isinstance(v, str) and v)

        content = spec.get("content", {})
        if isinstance(content, dict):
            envelope = content.get("envelope", {})
            if isinstance(envelope, dict):
                signatures = envelope.get("signatures", []) or []
                for signature in signatures:
                    if not isinstance(signature, dict):
                        continue
                    public_key = signature.get("publicKey") or signature.get("public_key")
                    if isinstance(public_key, dict):
                        content_value = public_key.get("content")
                        if content_value:
                            cert_b64_candidates.append(content_value)
                    elif public_key:
                        cert_b64_candidates.append(public_key)

        for cert_b64 in cert_b64_candidates:
            if cert_b64:
                cert_bytes = base64.b64decode(cert_b64)
                try:
                    cert = x509.load_pem_x509_certificate(cert_bytes)
                except ValueError:
                    cert = x509.load_der_x509_certificate(cert_bytes)

                try:
                    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
                    emails = san.get_values_for_type(x509.RFC822Name)
                    if emails:
                        return emails[0]
                    uris = san.get_values_for_type(x509.UniformResourceIdentifier)
                    if uris:
                        return uris[0]
                except x509.ExtensionNotFound:
                    pass

                subject_emails = cert.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)
                if subject_emails:
                    return subject_emails[0].value
    except Exception as exc:
        logger.debug("Could not extract signer identity: %s", exc)
    return None


__all__ = [
    "_decode_attestation_payload",
    "_decode_dsse_payload",
    "_decode_rekor_body",
    "_extract_committed_payload_hash",
    "_extract_signer_identity",
]
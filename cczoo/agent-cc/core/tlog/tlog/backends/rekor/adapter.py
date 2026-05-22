import base64
import hashlib
import json
import logging
import os
import time
from typing import Any, Optional, Tuple
from urllib.parse import urlencode
import urllib.error
import urllib.request

import rekor_types
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat, load_pem_public_key
from sigstore._internal.merkle import verify_merkle_inclusion
from sigstore._internal.rekor.checkpoint import verify_checkpoint
from sigstore._internal.trust import Keyring
from sigstore.errors import VerificationError
from sigstore.models import LogEntry
from sigstore.models import Bundle
from sigstore_protobuf_specs.dev.sigstore.common.v1 import PublicKey as SigstorePublicKey
from sigstore_protobuf_specs.dev.sigstore.common.v1 import PublicKeyDetails

from tlog.immutable import ImmutableLogAdapter
from .oci_mirror import OciBundleMirror

logger = logging.getLogger(__name__)


class SigstoreLogAdapter(ImmutableLogAdapter):
    _bundle_entry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    _SUPPORTED_ENTRY_TYPES = {"dsse", "intoto"}
    _CHECKPOINT_PUBLIC_KEY_FILE_ENV = "TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_FILE"
    _CHECKPOINT_PUBLIC_KEY_PEM_ENV = "TC_API_REKOR_CHECKPOINT_PUBLIC_KEY_PEM"

    def __init__(
        self,
        rekor_url: str = "https://rekor.sigstore.dev",
        bundle_mirror_dir: Optional[str] = None,
        bundle_mirror: Optional[OciBundleMirror] = None,
        rekor_entry_type: Optional[str] = None,
    ):
        self.rekor_url = rekor_url
        self.bundle_mirror = bundle_mirror or (OciBundleMirror(bundle_mirror_dir) if bundle_mirror_dir else None)
        entry_type = (rekor_entry_type or os.environ.get("TC_API_REKOR_ENTRY_TYPE", "intoto")).strip().lower()
        if entry_type not in self._SUPPORTED_ENTRY_TYPES:
            supported = ", ".join(sorted(self._SUPPORTED_ENTRY_TYPES))
            raise ValueError(f"Unsupported Rekor entry type '{entry_type}'. Expected one of: {supported}")
        self.rekor_entry_type = entry_type
        self.raw_attestation_fetch_retries = max(
            0,
            int(os.environ.get("TC_API_REKOR_ATTESTATION_FETCH_RETRIES", "6")),
        )
        self.raw_attestation_fetch_backoff_seconds = max(
            0.0,
            float(os.environ.get("TC_API_REKOR_ATTESTATION_FETCH_BACKOFF_SECONDS", "0.5")),
        )
        self.payload_hash_lookup_retries = max(
            0,
            int(os.environ.get("TC_API_REKOR_PAYLOAD_LOOKUP_RETRIES", "3")),
        )
        self.payload_hash_lookup_backoff_seconds = max(
            0.0,
            float(os.environ.get("TC_API_REKOR_PAYLOAD_LOOKUP_BACKOFF_SECONDS", "2.0")),
        )
        self.payload_hash_lookup_timeout_seconds = max(
            1.0,
            float(os.environ.get("TC_API_REKOR_PAYLOAD_LOOKUP_TIMEOUT_SECONDS", "15")),
        )

    @classmethod
    def _cache_key(cls, rekor_url: str, log_id: str) -> tuple[str, str]:
        return rekor_url, log_id

    @staticmethod
    def _parse_log_reference(log_id: str) -> dict[str, Any]:
        if log_id.isdigit():
            return {"log_index": int(log_id)}
        return {"uuid": log_id}

    @staticmethod
    def _existing_bundle_reference(bundle: Bundle) -> tuple[Optional[str], Any]:
        try:
            log_entry = bundle.log_entry
        except Exception:
            return None, None

        uuid = getattr(log_entry, "uuid", None)
        if uuid:
            return str(uuid), log_entry

        log_index = getattr(log_entry, "log_index", None)
        if isinstance(log_index, int):
            return str(log_index), log_entry

        return None, log_entry

    @classmethod
    def _log_entry_kind(cls, entry: Any) -> Optional[str]:
        entry_candidate = entry
        if not isinstance(entry_candidate, dict) and hasattr(entry_candidate, "body"):
            entry_candidate = {"body": getattr(entry_candidate, "body")}
        entry_dict = cls._entry_to_dict(entry_candidate)
        body = cls._decode_body(entry_dict)
        kind = body.get("kind") if isinstance(body, dict) else None
        return kind.lower() if isinstance(kind, str) else None

    @staticmethod
    def _dsse_entry_from_bundle(bundle: Bundle) -> Optional[rekor_types.Dsse]:
        envelope = bundle._dsse_envelope
        if envelope is None:
            return None

        cert_pem = base64.b64encode(
            bundle.signing_certificate.public_bytes(Encoding.PEM)
        ).decode()

        return rekor_types.Dsse(
            spec=rekor_types.dsse.DsseSchema(
                proposed_content=rekor_types.dsse.ProposedContent(
                    envelope=envelope.to_json(),
                    verifiers=[cert_pem],
                )
            )
        )

    @staticmethod
    def _intoto_entry_from_bundle(bundle: Bundle) -> Optional[rekor_types.Intoto]:
        envelope = bundle._dsse_envelope
        if envelope is None:
            return None

        try:
            envelope_json = json.loads(envelope.to_json())
            envelope_bytes = envelope.to_json().encode("utf-8")
        except Exception:
            return None

        signatures = envelope_json.get("signatures")
        if not isinstance(signatures, list) or not signatures:
            return None

        cert_pem = base64.b64encode(
            bundle.signing_certificate.public_bytes(Encoding.PEM)
        ).decode()

        intoto_signatures = []
        for signature in signatures:
            if not isinstance(signature, dict):
                return None
            sig = signature.get("sig")
            if not isinstance(sig, str) or not sig:
                return None
            intoto_signatures.append(
                {
                    "keyid": signature.get("keyid"),
                    "sig": base64.b64encode(sig.encode("utf-8")).decode("utf-8"),
                    "publicKey": cert_pem,
                }
            )

        payload = envelope_json.get("payload")
        if not isinstance(payload, str) or not payload:
            return None

        return rekor_types.Intoto(
            api_version="0.0.2",
            spec=rekor_types.intoto.IntotoV002Schema(
                content={
                    "envelope": {
                        "payloadType": envelope_json.get("payloadType", "application/vnd.in-toto+json"),
                        "payload": base64.b64encode(payload.encode("utf-8")).decode("utf-8"),
                        "signatures": intoto_signatures,
                    },
                    "hash": {
                        "algorithm": "sha256",
                        "value": hashlib.sha256(envelope_bytes).hexdigest(),
                    }
                }
            )
        )

    def _proposed_entry_from_bundle(self, bundle: Bundle) -> Optional[Any]:
        if self.rekor_entry_type == "intoto":
            return self._intoto_entry_from_bundle(bundle)
        return self._dsse_entry_from_bundle(bundle)

    @staticmethod
    def build_intoto_entry_from_owner_key(
        envelope: dict,
        pub_key_pem: str,
    ) -> rekor_types.Intoto:
        """Build an intoto v0.0.2 proposed entry from an owner-key-signed DSSE envelope.

        *envelope* is a dict with keys payloadType, payload (base64), signatures.
        *pub_key_pem* is the PEM-encoded public key string.
        """
        envelope_json = json.dumps(envelope)
        envelope_bytes = envelope_json.encode("utf-8")

        pub_pem_b64 = base64.b64encode(pub_key_pem.encode("utf-8")).decode("utf-8")

        intoto_signatures = []
        for sig_entry in envelope["signatures"]:
            sig_b64 = sig_entry["sig"]
            intoto_signatures.append({
                "keyid": sig_entry.get("keyid", ""),
                "sig": base64.b64encode(sig_b64.encode("utf-8")).decode("utf-8"),
                "publicKey": pub_pem_b64,
            })

        payload_b64 = envelope["payload"]
        intoto_payload = base64.b64encode(payload_b64.encode("utf-8")).decode("utf-8")

        return rekor_types.Intoto(
            api_version="0.0.2",
            spec=rekor_types.intoto.IntotoV002Schema(
                content={
                    "envelope": {
                        "payloadType": envelope.get("payloadType", "application/vnd.in-toto+json"),
                        "payload": intoto_payload,
                        "signatures": intoto_signatures,
                    },
                    "hash": {
                        "algorithm": "sha256",
                        "value": hashlib.sha256(envelope_bytes).hexdigest(),
                    },
                }
            ),
        )

    @staticmethod
    def _entry_to_dict(entry: Any) -> Any:
        if not isinstance(entry, LogEntry):
            return entry

        result = {
            "uuid": entry.uuid,
            "entryUUID": entry.uuid,
            "log_id": entry.log_id,
            "logID": entry.log_id,
            "log_index": entry.log_index,
            "logIndex": entry.log_index,
            "integratedTime": entry.integrated_time,
            "body": str(entry.body),
            "verification": {
                "inclusionProof": {
                    "checkpoint": entry.inclusion_proof.checkpoint,
                    "hashes": entry.inclusion_proof.hashes,
                    "logIndex": entry.inclusion_proof.log_index,
                    "rootHash": entry.inclusion_proof.root_hash,
                    "treeSize": entry.inclusion_proof.tree_size,
                },
                "signedEntryTimestamp": entry.inclusion_promise,
            },
        }
        attestation = getattr(entry, "attestation", None)
        if attestation is not None:
            result["attestation"] = attestation
        return result

    @classmethod
    def _cache_bundle_entry(
        cls,
        rekor_url: str,
        log_id: str,
        bundle: Bundle,
        base_entry: Optional[Any] = None,
        alternate_ids: Optional[list[str]] = None,
    ) -> None:
        envelope = bundle._dsse_envelope
        if envelope is None:
            return

        try:
            envelope_json = json.loads(envelope.to_json())
        except Exception:
            return

        payload_b64 = envelope_json.get("payload")
        if not isinstance(payload_b64, str):
            return

        cert_b64 = base64.b64encode(
            bundle.signing_certificate.public_bytes(Encoding.PEM)
        ).decode()

        entry_dict = cls._entry_to_dict(base_entry if base_entry is not None else bundle.log_entry)
        if not isinstance(entry_dict, dict):
            entry_dict = {}

        body = entry_dict.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(base64.b64decode(body).decode("utf-8"))
            except Exception:
                body = {}
        if not isinstance(body, dict):
            body = {}

        spec = body.setdefault("spec", {})
        if not isinstance(spec, dict):
            spec = {}
            body["spec"] = spec
        spec["payload"] = payload_b64
        signatures = spec.get("signatures")
        if not isinstance(signatures, list) or not signatures:
            spec["signatures"] = [{"verifier": cert_b64}]
        elif isinstance(signatures[0], dict) and not signatures[0].get("verifier"):
            signatures[0]["verifier"] = cert_b64

        entry_dict["body"] = body
        entry_dict["_tc_replay_provenance"] = "cache-assisted"
        if log_id.isdigit():
            entry_dict["log_index"] = int(log_id)
            entry_dict["logIndex"] = int(log_id)
        else:
            entry_dict["uuid"] = log_id
            entry_dict["entryUUID"] = log_id

        ids_to_cache = [log_id]
        if alternate_ids:
            ids_to_cache.extend(alternate_ids)
        for item in ids_to_cache:
            if item:
                cls._bundle_entry_cache[cls._cache_key(rekor_url, str(item))] = entry_dict

    @classmethod
    def _get_cached_entry(cls, rekor_url: str, log_id: str) -> Optional[dict[str, Any]]:
        return cls._bundle_entry_cache.get(cls._cache_key(rekor_url, log_id))

    @staticmethod
    def _clone_cached_entry(entry: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(entry))

    @staticmethod
    def _payload_hash_from_entry(entry: Any) -> Optional[str]:
        body = entry.get("body", {}) if isinstance(entry, dict) else {}
        if isinstance(body, str):
            try:
                body = json.loads(base64.b64decode(body).decode("utf-8"))
            except Exception:
                body = {}
        if not isinstance(body, dict):
            return None
        payload_b64 = body.get("spec", {}).get("payload")
        if not isinstance(payload_b64, str):
            return None
        try:
            payload_bytes = base64.b64decode(payload_b64)
        except Exception:
            return None
        import hashlib

        return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()

    @staticmethod
    def _decode_body(entry: Any) -> dict[str, Any]:
        body = entry.get("body", {}) if isinstance(entry, dict) else {}
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                try:
                    return json.loads(base64.b64decode(body).decode("utf-8"))
                except Exception:
                    return {}
        return {}

    @classmethod
    def _normalize_raw_entry_response(cls, response_payload: Any) -> Optional[dict[str, Any]]:
        if not isinstance(response_payload, dict):
            return None
        if "body" in response_payload:
            return response_payload
        if len(response_payload) != 1:
            return None
        entry_id, entry = next(iter(response_payload.items()))
        if not isinstance(entry, dict):
            return None
        normalized = dict(entry)
        normalized.setdefault("uuid", str(entry_id))
        normalized.setdefault("entryUUID", str(entry_id))
        return normalized

    def _fetch_raw_rekor_entry(self, log_id: str) -> Optional[dict[str, Any]]:
        base_url = f"{self.rekor_url.rstrip('/')}/api/v1/log/entries"
        if log_id.isdigit():
            request_url = f"{base_url}?{urlencode({'logIndex': int(log_id)})}"
        else:
            request_url = f"{base_url}/{log_id}"

        request = urllib.request.Request(request_url, method="GET")
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return self._normalize_raw_entry_response(payload)

    @classmethod
    def _normalized_inclusion_proof(cls, raw_entry: dict[str, Any]) -> Optional[dict[str, Any]]:
        verification = raw_entry.get("verification") if isinstance(raw_entry, dict) else None
        if not isinstance(verification, dict):
            return None
        inclusion_proof = verification.get("inclusionProof")
        if not isinstance(inclusion_proof, dict):
            return None

        hashes = inclusion_proof.get("hashes")
        if not isinstance(hashes, list):
            hashes = []

        return {
            "log_index": inclusion_proof.get("logIndex"),
            "root_hash": inclusion_proof.get("rootHash"),
            "tree_size": inclusion_proof.get("treeSize"),
            "hashes": hashes,
            "checkpoint": inclusion_proof.get("checkpoint"),
            "signed_entry_timestamp": verification.get("signedEntryTimestamp"),
        }

    @classmethod
    def _wrapped_raw_entry_response(cls, log_id: str, raw_entry: dict[str, Any]) -> dict[str, Any]:
        entry_id = raw_entry.get("uuid") or raw_entry.get("entryUUID") or str(log_id)
        wrapped = dict(raw_entry)
        wrapped.setdefault("uuid", str(entry_id))
        wrapped.setdefault("entryUUID", str(entry_id))
        return {str(entry_id): wrapped}

    @classmethod
    def _log_entry_from_raw_entry(cls, log_id: str, raw_entry: dict[str, Any]) -> LogEntry:
        return LogEntry._from_response(cls._wrapped_raw_entry_response(log_id, raw_entry))

    @classmethod
    def _checkpoint_public_key_details(cls, public_key: Any) -> PublicKeyDetails:
        if isinstance(public_key, rsa.RSAPublicKey):
            key_size = public_key.key_size
            if key_size <= 2048:
                return PublicKeyDetails.PKIX_RSA_PKCS1V15_2048_SHA256
            if key_size <= 3072:
                return PublicKeyDetails.PKIX_RSA_PKCS1V15_3072_SHA256
            return PublicKeyDetails.PKIX_RSA_PKCS1V15_4096_SHA256

        if isinstance(public_key, ec.EllipticCurvePublicKey):
            curve = public_key.curve
            if isinstance(curve, ec.SECP256R1):
                return PublicKeyDetails.PKIX_ECDSA_P256_SHA_256
            if isinstance(curve, ec.SECP384R1):
                return PublicKeyDetails.PKIX_ECDSA_P384_SHA_384
            if isinstance(curve, ec.SECP521R1):
                return PublicKeyDetails.PKIX_ECDSA_P521_SHA_512

        raise VerificationError(f"unsupported Rekor checkpoint public key type: {type(public_key)!r}")

    @classmethod
    def _rekor_keyring_from_pem(cls, public_key_pem: str) -> Keyring:
        public_key = load_pem_public_key(public_key_pem.encode("utf-8"))
        der_bytes = public_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        sigstore_public_key = SigstorePublicKey(
            raw_bytes=der_bytes,
            key_details=cls._checkpoint_public_key_details(public_key),
        )
        return Keyring([sigstore_public_key])

    @classmethod
    def _load_checkpoint_public_key_pem(
        cls,
        explicit_pem: Optional[str] = None,
    ) -> tuple[Optional[str], Optional[str]]:
        if explicit_pem and explicit_pem.strip():
            return explicit_pem.strip(), "explicit-policy"

        pem_env = os.environ.get(cls._CHECKPOINT_PUBLIC_KEY_PEM_ENV, "").strip()
        if pem_env:
            return pem_env, cls._CHECKPOINT_PUBLIC_KEY_PEM_ENV

        pem_file = os.environ.get(cls._CHECKPOINT_PUBLIC_KEY_FILE_ENV, "").strip()
        if pem_file:
            with open(pem_file, "r", encoding="utf-8") as handle:
                return handle.read(), cls._CHECKPOINT_PUBLIC_KEY_FILE_ENV

        return None, None

    def verify_head_entry_inclusion(
        self,
        log_id: str,
        checkpoint_public_key_pem: Optional[str] = None,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {
            "status": "degraded",
            "scope": "accepted-head-only",
            "log_id": log_id,
            "entry_uuid": None,
            "log_index": None,
            "inclusion_status": "unavailable",
            "checkpoint_status": "unavailable",
            "checkpoint_origin": None,
            "bootstrap_trust": {
                "configured": False,
                "source": None,
                "consistency_proven": False,
            },
            "proof": None,
            "reasons": [],
        }

        try:
            raw_entry = self._fetch_raw_rekor_entry(log_id)
        except Exception as exc:
            result["reasons"].append(f"failed to fetch Rekor entry proof material: {exc}")
            return result

        if raw_entry is None:
            result["reasons"].append("Rekor entry proof material was unavailable")
            return result

        result["entry_uuid"] = raw_entry.get("uuid") or raw_entry.get("entryUUID")
        result["log_index"] = raw_entry.get("logIndex") or raw_entry.get("log_index")
        result["proof"] = self._normalized_inclusion_proof(raw_entry)

        if result["proof"] is None:
            result["checkpoint_status"] = "missing"
            result["reasons"].append("accepted head entry did not include Rekor inclusion proof material")
            return result

        checkpoint_text = result["proof"].get("checkpoint")
        if isinstance(checkpoint_text, str) and checkpoint_text.strip():
            checkpoint_header = checkpoint_text.strip().splitlines()
            if checkpoint_header:
                result["checkpoint_origin"] = checkpoint_header[0]

        try:
            log_entry = self._log_entry_from_raw_entry(log_id, raw_entry)
            verify_merkle_inclusion(log_entry)
            result["inclusion_status"] = "verified"
        except Exception as exc:
            result["status"] = "failed"
            result["inclusion_status"] = "failed"
            result["reasons"].append(f"accepted head inclusion proof was invalid: {exc}")
            return result

        trust_pem, trust_source = self._load_checkpoint_public_key_pem(checkpoint_public_key_pem)
        if not trust_pem:
            result["checkpoint_status"] = "unconfigured"
            result["reasons"].append("accepted head checkpoint trust source was not configured")
            return result

        try:
            keyring = self._rekor_keyring_from_pem(trust_pem)
            verify_checkpoint(keyring, log_entry)
        except Exception as exc:
            result["status"] = "failed"
            result["checkpoint_status"] = "invalid"
            result["bootstrap_trust"] = {
                "configured": True,
                "source": trust_source,
                "consistency_proven": False,
            }
            result["reasons"].append(f"accepted head checkpoint validation failed: {exc}")
            return result

        result["status"] = "verified"
        result["checkpoint_status"] = "verified"
        result["bootstrap_trust"] = {
            "configured": True,
            "source": trust_source,
            "consistency_proven": False,
        }
        return result

    @staticmethod
    def _merge_raw_entry_extras(entry_dict: dict[str, Any], raw_entry: Optional[dict[str, Any]]) -> dict[str, Any]:
        if raw_entry is None:
            return entry_dict
        merged_entry = dict(entry_dict)
        for key in ("attestation", "attestationType"):
            if key in raw_entry and (key not in merged_entry or not merged_entry.get(key)):
                merged_entry[key] = raw_entry[key]
        return merged_entry

    @classmethod
    def _needs_raw_attestation_retry(cls, entry_dict: dict[str, Any]) -> bool:
        if cls._entry_has_decodable_payload(entry_dict):
            return False
        if cls._decoded_attestation_payload_bytes(entry_dict.get("attestation")):
            return False
        return cls._committed_payload_hash_from_body(cls._decode_body(entry_dict)) is not None

    @classmethod
    def _public_payload_hash_from_entry(cls, entry: Any) -> Optional[str]:
        body = cls._decode_body(entry)
        spec = body.get("spec", {}) if isinstance(body, dict) else {}
        if not isinstance(spec, dict):
            return None
        payload_hash = spec.get("payloadHash")
        if isinstance(payload_hash, dict):
            algorithm = payload_hash.get("algorithm")
            value = payload_hash.get("value")
            if isinstance(algorithm, str) and isinstance(value, str):
                return f"{algorithm}:{value}"
        return None

    @classmethod
    def _entry_has_decodable_payload(cls, entry: Any) -> bool:
        body = cls._decode_body(entry)
        spec = body.get("spec", {}) if isinstance(body, dict) else {}
        if not isinstance(spec, dict):
            return False
        payload = spec.get("payload")
        if isinstance(payload, str):
            return True
        proposed_content = spec.get("proposedContent")
        if isinstance(proposed_content, dict) and isinstance(proposed_content.get("envelope"), str):
            return True
        content = spec.get("content")
        if isinstance(content, dict):
            envelope = content.get("envelope")
            if isinstance(envelope, dict) and isinstance(envelope.get("payload"), str):
                return True
        return False

    @classmethod
    def _committed_payload_hash_from_body(cls, body: dict[str, Any]) -> Optional[str]:
        if not isinstance(body, dict):
            return None
        spec = body.get("spec", {})
        if not isinstance(spec, dict):
            return None

        hash_sources = [spec.get("payloadHash")]
        content = spec.get("content")
        if isinstance(content, dict):
            hash_sources.append(content.get("payloadHash"))

        for payload_hash in hash_sources:
            if isinstance(payload_hash, dict):
                algorithm = payload_hash.get("algorithm") or payload_hash.get("algorithm")
                value = payload_hash.get("value")
                if isinstance(algorithm, str) and isinstance(value, str):
                    return f"{algorithm}:{value}"

        payload_b64 = spec.get("payload")
        if not isinstance(payload_b64, str) and isinstance(content, dict):
            envelope = content.get("envelope")
            if isinstance(envelope, dict):
                payload_b64 = envelope.get("payload")
        if not isinstance(payload_b64, str):
            return None
        try:
            payload_bytes = base64.b64decode(payload_b64)
        except Exception:
            return None
        import hashlib

        return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()

    @staticmethod
    def _decoded_attestation_payload_bytes(attestation: Any) -> Optional[bytes]:
        if attestation is None:
            return None
        if isinstance(attestation, dict):
            for key in ("payload", "data"):
                value = attestation.get(key)
                if isinstance(value, str):
                    try:
                        return base64.b64decode(value)
                    except Exception:
                        return value.encode("utf-8")
            envelope = attestation.get("envelope")
            if isinstance(envelope, dict):
                payload = envelope.get("payload")
                if isinstance(payload, str):
                    try:
                        return base64.b64decode(payload)
                    except Exception:
                        return payload.encode("utf-8")
            try:
                return json.dumps(attestation, separators=(",", ":")).encode("utf-8")
            except Exception:
                return None
        if isinstance(attestation, str):
            try:
                return base64.b64decode(attestation)
            except Exception:
                return attestation.encode("utf-8")
        return None

    @classmethod
    def _merge_attestation_payload_into_public_entry(cls, public_entry: dict[str, Any]) -> dict[str, Any]:
        if cls._entry_has_decodable_payload(public_entry):
            return public_entry

        body = cls._decode_body(public_entry)
        committed_payload_hash = cls._committed_payload_hash_from_body(body)
        attestation_bytes = cls._decoded_attestation_payload_bytes(public_entry.get("attestation"))
        if not committed_payload_hash or not attestation_bytes:
            return public_entry

        import hashlib

        observed_payload_hash = "sha256:" + hashlib.sha256(attestation_bytes).hexdigest()
        if observed_payload_hash != committed_payload_hash:
            return public_entry

        merged_entry = cls._clone_cached_entry(public_entry)
        merged_body = cls._decode_body(merged_entry)
        merged_spec = merged_body.get("spec", {}) if isinstance(merged_body, dict) else {}
        if not isinstance(merged_spec, dict):
            merged_spec = {}
        merged_spec["payload"] = base64.b64encode(attestation_bytes).decode("utf-8")
        merged_body["spec"] = merged_spec
        merged_entry["body"] = merged_body
        merged_entry["_tc_replay_provenance"] = "attestation-storage"
        return merged_entry

    @classmethod
    def _merge_cached_payload_into_public_entry(
        cls,
        rekor_url: str,
        log_id: str,
        public_entry: dict[str, Any],
    ) -> dict[str, Any]:
        cached_entry = cls._get_cached_entry(rekor_url, log_id)
        if cached_entry is None:
            return public_entry
        if cls._entry_has_decodable_payload(public_entry):
            return public_entry

        cached_payload_hash = cls._payload_hash_from_entry(cached_entry)
        public_payload_hash = cls._public_payload_hash_from_entry(public_entry)
        if not cached_payload_hash or not public_payload_hash or cached_payload_hash != public_payload_hash:
            return public_entry

        merged_entry = cls._clone_cached_entry(cached_entry)
        merged_body = cls._decode_body(merged_entry)
        public_body = cls._decode_body(public_entry)
        merged_spec = merged_body.get("spec", {}) if isinstance(merged_body, dict) else {}
        public_spec = public_body.get("spec", {}) if isinstance(public_body, dict) else {}
        if isinstance(merged_spec, dict) and isinstance(public_spec, dict):
            for key in ("payloadHash", "envelopeHash", "signatures"):
                if key in public_spec:
                    merged_spec[key] = public_spec[key]
            merged_body["spec"] = merged_spec
            merged_entry["body"] = merged_body
        for key in ("uuid", "entryUUID", "log_id", "logID", "log_index", "logIndex", "integratedTime", "verification"):
            if key in public_entry:
                merged_entry[key] = public_entry[key]
        merged_entry["_tc_replay_provenance"] = "cache-assisted"
        return merged_entry

    def _merge_mirror_payload_into_public_entry(self, public_entry: dict[str, Any]) -> dict[str, Any]:
        if self.bundle_mirror is None:
            return public_entry
        if self._entry_has_decodable_payload(public_entry):
            return public_entry

        public_payload_hash = self._public_payload_hash_from_entry(public_entry)
        if not public_payload_hash:
            return public_entry

        mirrored_record = self.bundle_mirror.resolve_bundle(public_payload_hash)
        if mirrored_record is None:
            return public_entry

        mirrored_entry = self._mirror_entry_from_bundle_record(mirrored_record)
        if mirrored_entry is None:
            return public_entry

        merged_entry = self._clone_cached_entry(mirrored_entry)
        merged_body = self._decode_body(merged_entry)
        public_body = self._decode_body(public_entry)
        merged_spec = merged_body.get("spec", {}) if isinstance(merged_body, dict) else {}
        public_spec = public_body.get("spec", {}) if isinstance(public_body, dict) else {}
        if isinstance(merged_spec, dict) and isinstance(public_spec, dict):
            for key in ("payloadHash", "envelopeHash", "signatures"):
                if key in public_spec:
                    merged_spec[key] = public_spec[key]
            merged_body["spec"] = merged_spec
            merged_entry["body"] = merged_body
        for key in ("uuid", "entryUUID", "log_id", "logID", "log_index", "logIndex", "integratedTime", "verification"):
            if key in public_entry:
                merged_entry[key] = public_entry[key]
        merged_entry["_tc_replay_provenance"] = "mirror"
        return merged_entry

    @classmethod
    def _find_cached_entry_by_payload_hash(cls, rekor_url: str, payload_hash: str) -> Optional[dict[str, Any]]:
        for (cached_rekor_url, _log_id), entry in cls._bundle_entry_cache.items():
            if cached_rekor_url != rekor_url:
                continue
            if cls._payload_hash_from_entry(entry) == payload_hash:
                return entry
        return None

    @staticmethod
    def _mirror_entry_from_bundle_record(record: dict[str, Any]) -> Optional[dict[str, Any]]:
        annotations = record.get("annotations") or {}
        payload_b64 = annotations.get("payload_b64")
        if not isinstance(payload_b64, str) or not payload_b64:
            return None

        body = {
            "apiVersion": "0.0.1",
            "kind": "dsse",
            "spec": {
                "payload": payload_b64,
                "signatures": [],
            },
        }
        return {
            "uuid": f"mirror-{record['payload_hash']}",
            "entryUUID": f"mirror-{record['payload_hash']}",
            "body": body,
            "integratedTime": None,
            "verification": None,
            "_tc_replay_provenance": "mirror",
            "_tc_mirror_artifact_digest": record.get("artifact_digest"),
        }

    @classmethod
    def _candidate_preference(cls, candidate: Any) -> tuple[int, int, int, int]:
        if not isinstance(candidate, dict):
            return (0, 0, 0, 0)
        body = cls._decode_body(candidate)
        materialized = int(
            cls._entry_has_decodable_payload(candidate)
            or cls._decoded_attestation_payload_bytes(candidate.get("attestation")) is not None
        )
        provenance = candidate.get("_tc_replay_provenance")
        provenance_rank = {
            "mirror": 3,
            "attestation-storage": 2,
            "cache-assisted": 1,
        }.get(provenance, 0)
        has_identity = int(bool(candidate.get("uuid") or candidate.get("entryUUID") or candidate.get("log_id") or candidate.get("logID")))
        has_payload_hash = int(
            cls._committed_payload_hash_from_body(body) is not None
            or cls._public_payload_hash_from_entry(candidate) is not None
        )
        return (materialized, provenance_rank, has_identity, has_payload_hash)

    @classmethod
    def _preferred_predecessor_candidate(cls, candidates: list[Any]) -> Optional[dict[str, Any]]:
        dict_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
        if not dict_candidates:
            return None
        return max(dict_candidates, key=cls._candidate_preference)
        
    def submit_bundle(self, bundle: str, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)

            if isinstance(bundle, str):
                bundle_obj = Bundle.from_json(bundle)
            else:
                bundle_obj = bundle
            existing_ref, log_entry = self._existing_bundle_reference(bundle_obj)
            existing_kind = self._log_entry_kind(log_entry) if log_entry is not None else None
            reuse_existing_entry = bool(existing_ref) and (
                existing_kind is None
                or existing_kind == self.rekor_entry_type
            )
            if reuse_existing_entry:
                entry_dict = self._entry_to_dict(log_entry)
                alternate_ids = []
                if getattr(log_entry, "uuid", None):
                    alternate_ids.append(str(log_entry.uuid))
                if getattr(log_entry, "log_index", None) is not None:
                    alternate_ids.append(str(log_entry.log_index))
                self._cache_bundle_entry(self.rekor_url, existing_ref, bundle_obj, log_entry, alternate_ids)
                return existing_ref, "confirmed", entry_dict

            proposed_entry = self._proposed_entry_from_bundle(bundle_obj)
            if proposed_entry is None:
                raise ValueError(
                    f"Bundle does not contain a valid DSSE envelope for Rekor {self.rekor_entry_type} submission"
                )

            entry = client.log.entries.post(proposed_entry)
            if getattr(entry, "uuid", None):
                log_id = str(entry.uuid)
                alternate_ids = [str(entry.log_index)] if getattr(entry, "log_index", None) is not None else []
                self._cache_bundle_entry(self.rekor_url, log_id, bundle_obj, entry, alternate_ids)
                return log_id, "confirmed", self._entry_to_dict(entry)
            if getattr(entry, "log_index", None) is not None:
                log_id = str(entry.log_index)
                alternate_ids = [str(entry.uuid)] if getattr(entry, "uuid", None) else []
                self._cache_bundle_entry(self.rekor_url, log_id, bundle_obj, entry, alternate_ids)
                return log_id, "confirmed", self._entry_to_dict(entry)

            return "unknown-id", "pending", self._entry_to_dict(entry)
            
        except Exception as e:
            logger.error(f"Failed to submit bundle to Rekor: {e}")
            raise

    def submit_owner_signed_entry(
        self,
        envelope: dict,
        pub_key_pem: str,
    ) -> Tuple[str, int, dict]:
        """Submit an owner-key-signed DSSE envelope to Rekor as intoto v0.0.2.

        Returns (uuid, log_index, entry_dict).
        """
        proposed = self.build_intoto_entry_from_owner_key(envelope, pub_key_pem)
        payload = proposed.model_dump(mode="json", by_alias=True)

        url = f"{self.rekor_url}/api/v1/log/entries"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"Rekor submit_owner_signed_entry failed: HTTP {exc.code} — {error_body}"
            ) from exc

        uuid = next(iter(result))
        entry = result[uuid]
        log_index = entry.get("logIndex", -1)
        return uuid, log_index, entry

    def get_entry(self, log_id: str) -> Any:
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            entry = client.log.entries.get(**self._parse_log_reference(log_id))
            entry_dict = self._entry_to_dict(entry)
            if isinstance(entry_dict, dict):
                raw_entry = None
                fetch_attempts = self.raw_attestation_fetch_retries + 1
                for attempt in range(fetch_attempts):
                    try:
                        raw_entry = self._fetch_raw_rekor_entry(log_id)
                    except Exception as raw_exc:
                        logger.debug("Could not fetch raw Rekor entry extras for %s: %s", log_id, raw_exc)
                        break

                    entry_dict = self._merge_raw_entry_extras(entry_dict, raw_entry)
                    if not self._needs_raw_attestation_retry(entry_dict):
                        break
                    if attempt + 1 < fetch_attempts and self.raw_attestation_fetch_backoff_seconds > 0:
                        time.sleep(self.raw_attestation_fetch_backoff_seconds)

                merged_entry = self._merge_attestation_payload_into_public_entry(entry_dict)
                merged_entry = self._merge_mirror_payload_into_public_entry(merged_entry)
                merged_entry = self._merge_cached_payload_into_public_entry(self.rekor_url, log_id, merged_entry)
                return merged_entry
            return entry_dict
        except Exception as e:
            cached_entry = self._get_cached_entry(self.rekor_url, log_id)
            if cached_entry is not None:
                logger.warning(
                    "Falling back to process-local cached Rekor entry for %s after public fetch failure: %s",
                    log_id,
                    e,
                )
                return self._clone_cached_entry(cached_entry)
            logger.error(f"Failed to get entry {log_id} from Rekor: {e}")
            raise

    def find_entries_by_payload_hash(self, payload_hash: str) -> list[Any]:
        results: list[Any] = []
        seen_ids: set[str] = set()

        request_body = json.dumps({"hash": payload_hash}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.rekor_url.rstrip('/')}/api/v1/index/retrieve",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        public_lookup_failed = False
        response_data: Any = []
        max_attempts = self.payload_hash_lookup_retries + 1
        for attempt in range(1, max_attempts + 1):
            retryable_empty_result = False
            try:
                with urllib.request.urlopen(request, timeout=self.payload_hash_lookup_timeout_seconds) as response:
                    response_data = json.loads(response.read().decode("utf-8"))
                if isinstance(response_data, dict):
                    lookup_entries = response_data.get("entries") or response_data.get("ids") or response_data.get("uuids") or []
                elif isinstance(response_data, list):
                    lookup_entries = response_data
                else:
                    lookup_entries = []
                retryable_empty_result = not lookup_entries
                if not retryable_empty_result or attempt == max_attempts:
                    break
                logger.warning(
                    "Rekor payload-hash lookup returned no entries for %s on attempt %s/%s; retrying",
                    payload_hash,
                    attempt,
                    max_attempts,
                )
            except urllib.error.HTTPError as exc:
                public_lookup_failed = True
                response_data = []
                retryable_status = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
                if retryable_status and attempt < max_attempts:
                    logger.warning(
                        "Rekor payload-hash lookup failed for %s: HTTP %s on attempt %s/%s; retrying",
                        payload_hash,
                        exc.code,
                        attempt,
                        max_attempts,
                    )
                else:
                    logger.warning("Rekor payload-hash lookup failed for %s: HTTP %s", payload_hash, exc.code)
                    break
            except Exception as exc:
                public_lookup_failed = True
                response_data = []
                if attempt < max_attempts:
                    logger.warning(
                        "Rekor payload-hash lookup failed for %s: %s on attempt %s/%s; retrying",
                        payload_hash,
                        exc,
                        attempt,
                        max_attempts,
                    )
                else:
                    logger.warning("Rekor payload-hash lookup failed for %s: %s", payload_hash, exc)
                    break

            if attempt < max_attempts and self.payload_hash_lookup_backoff_seconds > 0:
                time.sleep(self.payload_hash_lookup_backoff_seconds)

        if isinstance(response_data, dict):
            candidate_ids = response_data.get("entries") or response_data.get("ids") or response_data.get("uuids") or []
        elif isinstance(response_data, list):
            candidate_ids = response_data
        else:
            candidate_ids = []

        for attempt in range(1, max_attempts + 1):
            results = []
            seen_ids = set()
            for candidate_id in candidate_ids:
                if not isinstance(candidate_id, (str, int)):
                    continue
                candidate_key = str(candidate_id)
                if candidate_key in seen_ids:
                    continue
                try:
                    entry = self.get_entry(candidate_key)
                except Exception as exc:
                    logger.warning("Failed to materialize Rekor candidate %s for %s: %s", candidate_key, payload_hash, exc)
                    continue
                seen_ids.add(candidate_key)
                results.append(entry)

            materialized_results = [
                entry
                for entry in results
                if isinstance(entry, dict)
                and (
                    self._entry_has_decodable_payload(entry)
                    or self._decoded_attestation_payload_bytes(entry.get("attestation")) is not None
                )
            ]
            retryable_unmaterialized_result = bool(candidate_ids) and not materialized_results
            if not retryable_unmaterialized_result or attempt == max_attempts:
                break
            logger.warning(
                "Rekor payload-hash lookup returned only unmaterialized candidates for %s on attempt %s/%s; retrying",
                payload_hash,
                attempt,
                max_attempts,
            )
            if self.payload_hash_lookup_backoff_seconds > 0:
                time.sleep(self.payload_hash_lookup_backoff_seconds)

        cached_entry = self._find_cached_entry_by_payload_hash(self.rekor_url, payload_hash)
        if cached_entry is not None:
            if public_lookup_failed or not candidate_ids:
                results.append(self._clone_cached_entry(cached_entry))

        if self.bundle_mirror is not None:
            mirrored_record = self.bundle_mirror.resolve_bundle(payload_hash)
            if mirrored_record is not None:
                mirrored_entry = self._mirror_entry_from_bundle_record(mirrored_record)
                if mirrored_entry is not None:
                    results.append(mirrored_entry)

        return results

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        results = []
        current_id = end_log_id
        seen_ids = set()
        
        try:
            for _ in range(count):
                if not current_id:
                    break

                current_key = str(current_id)
                if current_key in seen_ids:
                    break
                seen_ids.add(current_key)

                entry = self.get_entry(current_id)
                if not entry:
                    break

                # Older mocked responses may still use the raw {uuid: entry} shape.
                if isinstance(entry, dict) and "body" not in entry and len(entry) == 1:
                    val = next(iter(entry.values()))
                else:
                    val = entry
                results.append(val)
                
                # Extract previous link depending on the type of entry
                # hashedrekord entries have different structures than dsse
                body = val.get("body", {})
                if isinstance(body, str):
                    try:
                        import base64
                        body = json.loads(base64.b64decode(body).decode('utf-8'))
                    except Exception:
                        pass
                
                # DSSE or intoto
                dsse_payload = body.get("spec", {}).get("payload")
                if isinstance(dsse_payload, str):
                    try:
                        import base64
                        payload = json.loads(base64.b64decode(dsse_payload).decode('utf-8'))
                        predicate = payload.get("predicate", {})
                        
                        # Fallback parsing handling how we created it 
                        if "prev_log_id" in predicate:
                            current_id = predicate.get("prev_log_id")
                        elif "prev_log_id" in payload:
                            current_id = payload.get("prev_log_id")
                        elif "prev_lookup_hash" in predicate:
                            candidates = self.find_entries_by_payload_hash(predicate.get("prev_lookup_hash"))
                            if candidates:
                                candidate = self._preferred_predecessor_candidate(candidates)
                                current_id = candidate.get("uuid") or candidate.get("log_id") or candidate.get("entry_id")
                            else:
                                current_id = None
                        else:
                            current_id = None
                            
                    except Exception as e:
                        logger.warning(f"Could not parse payload for link: {e}")
                        current_id = None
                else:
                    # Generic fallback if not dsse
                    current_id = None

        except Exception as e:
            logger.error(f"Traverse hit an error: {e}")
            
        return results

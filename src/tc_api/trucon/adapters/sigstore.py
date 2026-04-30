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
from cryptography.hazmat.primitives.serialization import Encoding
from sigstore.models import LogEntry
from sigstore.models import Bundle

from tc_api.tlog.immutable import ImmutableLogAdapter
from tc_api.trucon.adapters.oci_mirror import OciBundleMirror

logger = logging.getLogger(__name__)


class SigstoreLogAdapter(ImmutableLogAdapter):
    _bundle_entry_cache: dict[tuple[str, str], dict[str, Any]] = {}
    _SUPPORTED_ENTRY_TYPES = {"dsse", "intoto"}

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
        
    def submit_bundle(self, bundle: Bundle, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)

            existing_ref, log_entry = self._existing_bundle_reference(bundle)
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
                self._cache_bundle_entry(self.rekor_url, existing_ref, bundle, log_entry, alternate_ids)
                return existing_ref, "confirmed", entry_dict

            proposed_entry = self._proposed_entry_from_bundle(bundle)
            if proposed_entry is None:
                raise ValueError(
                    f"Bundle does not contain a valid DSSE envelope for Rekor {self.rekor_entry_type} submission"
                )

            entry = client.log.entries.post(proposed_entry)
            if getattr(entry, "uuid", None):
                log_id = str(entry.uuid)
                alternate_ids = [str(entry.log_index)] if getattr(entry, "log_index", None) is not None else []
                self._cache_bundle_entry(self.rekor_url, log_id, bundle, entry, alternate_ids)
                return log_id, "confirmed", self._entry_to_dict(entry)
            if getattr(entry, "log_index", None) is not None:
                log_id = str(entry.log_index)
                alternate_ids = [str(entry.uuid)] if getattr(entry, "uuid", None) else []
                self._cache_bundle_entry(self.rekor_url, log_id, bundle, entry, alternate_ids)
                return log_id, "confirmed", self._entry_to_dict(entry)

            return "unknown-id", "pending", self._entry_to_dict(entry)
            
        except Exception as e:
            logger.error(f"Failed to submit bundle to Rekor: {e}")
            raise

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
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.warning("Rekor payload-hash lookup failed for %s: HTTP %s", payload_hash, exc.code)
            public_lookup_failed = True
            response_data = []
        except Exception as exc:
            logger.warning("Rekor payload-hash lookup failed for %s: %s", payload_hash, exc)
            public_lookup_failed = True
            response_data = []

        if isinstance(response_data, dict):
            candidate_ids = response_data.get("entries") or response_data.get("ids") or response_data.get("uuids") or []
        elif isinstance(response_data, list):
            candidate_ids = response_data
        else:
            candidate_ids = []

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
                                candidate = candidates[0]
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

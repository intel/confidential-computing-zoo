import base64
import json
import logging
from typing import Any, Optional, Tuple
import urllib.error
import urllib.request

import rekor_types
from cryptography.hazmat.primitives.serialization import Encoding
from sigstore.models import LogEntry
from sigstore.models import Bundle

from tc_api.tlog.immutable import ImmutableLogAdapter

logger = logging.getLogger(__name__)


class SigstoreLogAdapter(ImmutableLogAdapter):
    _bundle_entry_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def __init__(self, rekor_url: str = "https://rekor.sigstore.dev"):
        self.rekor_url = rekor_url

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

    @staticmethod
    def _proposed_entry_from_bundle(bundle: Bundle) -> Optional[rekor_types.Dsse]:
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
    def _entry_to_dict(entry: Any) -> Any:
        if not isinstance(entry, LogEntry):
            return entry

        return {
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

    @classmethod
    def _find_cached_entry_by_payload_hash(cls, rekor_url: str, payload_hash: str) -> Optional[dict[str, Any]]:
        for (cached_rekor_url, _log_id), entry in cls._bundle_entry_cache.items():
            if cached_rekor_url != rekor_url:
                continue
            if cls._payload_hash_from_entry(entry) == payload_hash:
                return entry
        return None
        
    def submit_bundle(self, bundle: Bundle, prev_log_id: Optional[str] = None) -> Tuple[str, str, Any]:
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)

            existing_ref, log_entry = self._existing_bundle_reference(bundle)
            if existing_ref:
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
                raise ValueError("Bundle does not contain a DSSE envelope and cannot be submitted")

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
            return self._entry_to_dict(entry)
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

        if results:
            return results

        cached_entry = self._find_cached_entry_by_payload_hash(self.rekor_url, payload_hash)
        if cached_entry is not None:
            if public_lookup_failed or not candidate_ids:
                results.append(self._clone_cached_entry(cached_entry))

        return results

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        results = []
        current_id = end_log_id
        
        try:
            for _ in range(count):
                if not current_id:
                    break

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

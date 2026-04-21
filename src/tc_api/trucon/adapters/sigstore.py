import base64
import json
import logging
from typing import Any, Optional, Tuple

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
            cached_entry = self._get_cached_entry(self.rekor_url, log_id)
            if cached_entry is not None:
                return cached_entry

            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            entry = client.log.entries.get(**self._parse_log_reference(log_id))
            return self._entry_to_dict(entry)
        except Exception as e:
            logger.error(f"Failed to get entry {log_id} from Rekor: {e}")
            raise

    def traverse(self, end_log_id: str, count: int = 10) -> list[Any]:
        results = []
        current_id = end_log_id
        
        try:
            from sigstore._internal.rekor.client import RekorClient
            client = RekorClient(self.rekor_url)
            
            for _ in range(count):
                if not current_id:
                    break

                entry = self._get_cached_entry(self.rekor_url, current_id)
                if entry is None:
                    entry = client.log.entries.get(**self._parse_log_reference(current_id))
                    if not entry:
                        break
                    entry = self._entry_to_dict(entry)

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

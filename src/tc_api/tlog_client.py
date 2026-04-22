import hashlib
import json
import logging
import os
import threading
import uuid
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

from cryptography import x509
from cryptography.x509.oid import NameOID
from sigstore.sign import SigningContext
from sigstore.oidc import IdentityToken
from sigstore.dsse import StatementBuilder, Subject
from sigstore.models import Bundle

from .sigstore_baseline import build_baseline_sigstore_bundle, build_signing_context
from .tlog.types import (
    RecordContext, Entry, Record, EventLog, CommitResult,
    CommitQueueStatus, LatestState, VerificationResult, SubmitStatus
)
from .tlog.errors import RecordNotFoundError, BackendSubmitError, VerificationError
from .trucon.internal_transport import request_json

logger = logging.getLogger(__name__)

def canonical_json(data: Any) -> str:
    """Return a highly deterministic JSON serialization for hashing."""
    return json.dumps(data, separators=(',', ':'), sort_keys=True, ensure_ascii=False)


def compute_entry_digest(key: str, value: Any) -> str:
    """Compute SHA-384 digest of a single entry: SHA384(canonical({"key": k, "value": v}))."""
    payload = canonical_json({"key": key, "value": value})
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


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


def _normalize_verification_entry(entry: Dict[str, Any], index: int, expected_identity: Optional[str]) -> Dict[str, Any]:
    body = _decode_rekor_body(entry)
    payload = _decode_dsse_payload(body)
    predicate = payload.get("predicate", {}) if isinstance(payload, dict) else {}
    subject = payload.get("subject", []) if isinstance(payload, dict) else []
    subject_names = [item.get("name") for item in subject if isinstance(item, dict) and item.get("name")]
    signer_identity = _extract_signer_identity(entry)
    signer_match = None if expected_identity is None else signer_identity == expected_identity
    payload_hash = None
    spec = body.get("spec", {}) if isinstance(body, dict) else {}
    encoded_payload = spec.get("payload") if isinstance(spec, dict) else None
    if isinstance(encoded_payload, str):
        try:
            import base64

            payload_hash = "sha256:" + hashlib.sha256(base64.b64decode(encoded_payload)).hexdigest()
        except Exception:
            payload_hash = None

    return {
        "index": index,
        "entry_id": entry.get("log_id") or entry.get("uuid") or entry.get("entryUUID"),
        "subject_names": subject_names,
        "event_id": predicate.get("event_id"),
        "event_type": predicate.get("event_type"),
        "chain_id": predicate.get("chain_id"),
        "sequence_num": predicate.get("sequence_num"),
        "digest": predicate.get("digest"),
        "predicate_entries": predicate.get("entries", []),
        "created": predicate.get("created"),
        "prev_event_digest": predicate.get("prev_event_digest"),
        "prev_lookup_hash": predicate.get("prev_lookup_hash"),
        "payload_hash": payload_hash,
        "candidate_count": None,
        "materialized_candidate_count": None,
        "matched_candidate_count": None,
        "predecessor_ok": None,
        "predecessor_status": None,
        "public_history_ok": None,
        "public_history_status": None,
        "replay_provenance": entry.get("_tc_replay_provenance", "public"),
        "prev_log_id": predicate.get("prev_log_id") or payload.get("prev_log_id"),
        "signer_identity": signer_identity,
        "signer_identity_match": signer_match,
        "included": signer_match is not False,
        "errors": [],
    }


def _entry_has_required_history_fields(entry: Dict[str, Any]) -> bool:
    return all(
        entry.get(field) is not None
        for field in ("event_id", "event_type", "sequence_num", "digest")
    )


def _entry_has_event_log0_baseline(entry: Dict[str, Any]) -> bool:
    if entry.get("event_type") != "chain.init":
        return True
    observed = {
        item.get("key")
        for item in entry.get("predicate_entries", [])
        if isinstance(item, dict)
    }
    return {"baseline_rtmr", "ccel_digest", "pub_key"}.issubset(observed)


def _classify_public_history_status(entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("replay_provenance") == "cache-assisted":
        return "cache-assisted"
    if not _entry_has_required_history_fields(entry):
        return "unmaterialized"
    if not _entry_has_event_log0_baseline(entry):
        return "baseline-missing"
    return None


def compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: List[str]) -> str:
    """Compute SHA-384 event digest over metadata + entry digests (two-level algorithm)."""
    payload = canonical_json({
        "created": created_iso,
        "entry_digests": entry_digests,
        "event_id": event_id,
        "event_type": event_type,
    })
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


def _candidate_identity(candidate: Dict[str, Any]) -> str:
    entry_id = candidate.get("entry_id")
    payload_hash = candidate.get("payload_hash")
    return f"{entry_id}|{payload_hash}"


def _has_signed_predecessor_contract(entry: Dict[str, Any]) -> bool:
    sequence_num = entry.get("sequence_num")
    return isinstance(sequence_num, int) and sequence_num > 1 and (
        entry.get("prev_event_digest") is not None or entry.get("prev_lookup_hash") is not None
    )


def _classify_replay_boundary(current: Dict[str, Any], entries: List[Dict[str, Any]]) -> Optional[str]:
    sequence_num = current.get("sequence_num")
    if not isinstance(sequence_num, int) or sequence_num <= 1:
        return None
    if _has_signed_predecessor_contract(current):
        return None

    lower_signed = any(
        _has_signed_predecessor_contract(entry) and entry.get("sequence_num") < sequence_num
        for entry in entries
    )
    if lower_signed:
        return "invalid"

    higher_signed = any(
        _has_signed_predecessor_contract(entry) and entry.get("sequence_num") > sequence_num
        for entry in entries
    )
    if higher_signed:
        return "degraded"

    return None


def _materialize_predecessor_candidates(
    current: Dict[str, Any],
    entries: List[Dict[str, Any]],
    immutable_log: Any,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    payload_hash = current.get("prev_lookup_hash")
    if not isinstance(payload_hash, str) or not payload_hash:
        return [], None

    candidate_sources: List[Dict[str, Any]] = []
    for entry in entries:
        if entry is current:
            continue
        if entry.get("payload_hash") == payload_hash:
            candidate_sources.append(dict(entry))

    finder = getattr(immutable_log, "find_entries_by_payload_hash", None)
    if callable(finder):
        try:
            discovered = finder(payload_hash)
        except Exception as exc:
            return candidate_sources, str(exc)
        for raw_entry in discovered or []:
            normalized = _normalize_verification_entry(raw_entry, 0, None)
            candidate_sources.append(normalized)

    deduped: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidate_sources:
        candidate_key = _candidate_identity(candidate)
        if candidate_key in seen:
            continue
        seen.add(candidate_key)
        deduped.append(candidate)
    return deduped, None


def _annotate_predecessor_verification(entries: List[Dict[str, Any]], immutable_log: Any) -> List[Dict[str, Any]]:
    """Annotate head->tail replay entries with signed predecessor verification details."""
    annotated: List[Dict[str, Any]] = []

    for entry in entries:
        current = dict(entry)
        sequence_num = current.get("sequence_num")
        prev_event_digest = current.get("prev_event_digest")
        prev_lookup_hash = current.get("prev_lookup_hash")
        public_history_status = _classify_public_history_status(current)

        if public_history_status is not None:
            current["public_history_ok"] = False
            current["public_history_status"] = public_history_status
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_ok"] = False
            current["predecessor_status"] = "unsupported"
            if public_history_status == "cache-assisted":
                current.setdefault("errors", []).append(
                    "Historical replay facts came from process-local cache rather than Rekor-auditable materialization"
                )
            elif public_history_status == "baseline-missing":
                current.setdefault("errors", []).append(
                    "Event Log 0 baseline facts were not recoverable from Rekor-auditable replay material"
                )
            else:
                current.setdefault("errors", []).append(
                    "Verifier-critical historical replay facts were not materialized from public Rekor entry data"
                )
            annotated.append(current)
            continue

        current["public_history_ok"] = True
        current["public_history_status"] = "public"

        if sequence_num == 1 and prev_event_digest is None and prev_lookup_hash is None:
            current["predecessor_ok"] = True
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "origin"
            annotated.append(current)
            continue

        if not isinstance(sequence_num, int) or sequence_num < 1:
            current["predecessor_ok"] = None
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unverifiable"
            current.setdefault("errors", []).append("Replay entry is missing a valid sequence_num")
            annotated.append(current)
            continue

        if prev_event_digest is None and prev_lookup_hash is None:
            boundary_status = _classify_replay_boundary(current, entries)
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unverifiable"
            if boundary_status is not None:
                current["boundary_status"] = boundary_status
                current["predecessor_ok"] = False if boundary_status == "invalid" else None
                if boundary_status == "invalid":
                    current.setdefault("errors", []).append(
                        "Signed predecessor contract regressed after reservation-backed replay began"
                    )
                else:
                    current.setdefault("errors", []).append(
                        "Signed predecessor contract unavailable at legacy-to-reservation replay boundary"
                    )
            else:
                current["predecessor_ok"] = None
            annotated.append(current)
            continue

        candidates, lookup_error = _materialize_predecessor_candidates(current, entries, immutable_log)
        current["candidate_count"] = len(candidates)
        current["materialized_candidate_count"] = len(candidates)

        if lookup_error is not None:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "lookup_failed"
            current.setdefault("errors", []).append(f"Predecessor candidate lookup failed: {lookup_error}")
            annotated.append(current)
            continue

        if current["candidate_count"] == 0:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "missing"
            current.setdefault("errors", []).append("Missing predecessor entry for signed replay contract")
            annotated.append(current)
            continue

        materialized_candidates = [
            candidate
            for candidate in candidates
            if candidate.get("sequence_num") is not None
            and candidate.get("digest") is not None
            and candidate.get("payload_hash") is not None
        ]
        current["materialized_candidate_count"] = len(materialized_candidates)
        if materialized_candidates and len(materialized_candidates) != len(candidates):
            current.setdefault("errors", []).append(
                "Some predecessor candidates could not be normalized into replayable entries"
            )
        if not materialized_candidates:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "decode_failed"
            current.setdefault("errors", []).append(
                "Discovered predecessor candidates could not be normalized into replayable entries"
            )
            annotated.append(current)
            continue

        public_candidates = [
            candidate
            for candidate in materialized_candidates
            if _classify_public_history_status(candidate) is None
        ]
        if not public_candidates:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unsupported"
            current.setdefault("errors", []).append(
                "Predecessor proof depended on cache-assisted or otherwise non-public candidate materialization"
            )
            annotated.append(current)
            continue

        matches = [
            candidate
            for candidate in public_candidates
            if current.get("chain_id") == candidate.get("chain_id")
            and sequence_num == candidate.get("sequence_num", 0) + 1
            and prev_event_digest == candidate.get("digest")
            and prev_lookup_hash == candidate.get("payload_hash")
        ]
        current["matched_candidate_count"] = len(matches)
        if len(matches) == 1:
            current["predecessor_ok"] = True
            current["predecessor_status"] = "proven"
        elif len(matches) > 1:
            current["predecessor_ok"] = False
            current["predecessor_status"] = "ambiguous"
            current.setdefault("errors", []).append(
                "Multiple predecessor candidates matched the signed replay contract"
            )
        else:
            current["predecessor_ok"] = False
            current["predecessor_status"] = "missing"
            current.setdefault("errors", []).append(
                "Signed predecessor contract did not match the replayed predecessor entry"
            )
        annotated.append(current)

    return annotated


# TruCon URL — loaded from config at module level
try:
    from .config import TRUCON_URL
except ImportError:
    TRUCON_URL = "http://127.0.0.1:8001"

class TrustedLogAPI:
    """
    tc_api-side committer. Performs DSSE signing locally and delegates
    sequencing (RTMR extend + SQLite INSERT) to TruCon via REST.
    
    Process-local state (_records, _entries) is used only for the multi-step
    init_record → add_entry → commit_record flow within a single request.
    No cross-request state is maintained.
    """
    def __init__(self, local_mr=None, immutable_log=None, trucon_url: Optional[str] = None) -> None:
        self.local_mr = local_mr  # Kept for backward compat; not used in commit path
        self.immutable_log = immutable_log  # Kept for verification
        self._trucon_url = trucon_url or TRUCON_URL
        # Per-request scratch space (not shared across workers)
        self._records: Dict[str, RecordContext] = {}
        self._entries: Dict[str, List[Entry]] = {}

    def init_record(self, prev_log_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> RecordContext:
        record_id = str(uuid.uuid4())
        ctx = RecordContext(
            record_id=record_id,
            chain_ref=context.get("chain_ref") if context else None,
            created_at=datetime.utcnow(),
            prev_log_id=prev_log_id
        )
        self._records[record_id] = ctx
        self._entries[record_id] = []
        return ctx

    def add_entry(self, record_id: str, entry: Entry) -> int:
        if record_id not in self._entries:
            raise RecordNotFoundError(f"Record {record_id} not found", code="NOT_FOUND", stage="add_entry", retryable=False)
        self._entries[record_id].append(entry)
        return len(self._entries[record_id])

    def commit_record(
        self,
        record_id: str,
        event_type: str,
        event_id: Optional[str] = None,
        commit_options: Optional[Dict[str, Any]] = None,
        instance_id: Optional[str] = None,
    ) -> CommitResult:
        if record_id not in self._records:
            raise RecordNotFoundError(f"Record {record_id} not found", code="NOT_FOUND", stage="commit", retryable=False)

        ctx = self._records[record_id]
        entries = self._entries[record_id]
        event_id = event_id or f"evt-{uuid.uuid4().hex[:8]}"
        chain_id = ctx.chain_ref or "default"

        # Generate idempotency key for retry safety
        idempotency_key = (commit_options or {}).get("idempotency_key") or f"idk-{uuid.uuid4().hex[:12]}"

        if chain_id != "default":
            self.init_chain(chain_id)

        reservation = self._reserve_commit_intent(chain_id=chain_id, idempotency_key=idempotency_key)
        if reservation.get("committed"):
            self._records.pop(record_id, None)
            self._entries.pop(record_id, None)
            return CommitResult(
                record_id=reservation.get("record_id", record_id),
                event_id=event_id,
                queue_status=SubmitStatus.PENDING,
                mr_value=None,
                prev_mr_value=None,
            )
        
        # Build canonical ordered entries
        record = Record(entries=entries)
        
        event_log = EventLog(
            event_id=event_id,
            event_type=event_type,
            digest="",
            record=record,
            created=datetime.utcnow(),
            global_id=None,
            signature=None,
            pub_key=None
        )

        # In-Toto payload formatting — prev_log_id EXCLUDED from signed predicate
        # Two-level digest: per-entry digests first, then event digest over metadata + entry digests
        entry_digests = [compute_entry_digest(e.key, e.value) for e in entries]
        created_iso = event_log.created.isoformat()
        event_digest = compute_event_digest(event_log.event_id, event_log.event_type, created_iso, entry_digests)
        event_log.digest = event_digest

        predicate_payload = {
            "event_id": event_log.event_id,
            "event_type": event_log.event_type,
            "created": created_iso,
            "entries": [{"key": e.key, "value": e.value} for e in entries],
            "entry_digests": entry_digests,
            "digest": event_digest,
            "chain_id": chain_id,
            "sequence_num": reservation["sequence_num"],
            "prev_event_digest": reservation.get("prev_event_digest"),
            "prev_lookup_hash": reservation.get("prev_lookup_hash"),
        }
        
        # Identity Token retrieval
        identity_token_str = (commit_options or {}).get("identity_token")
        if not identity_token_str:
            raise ValueError("Identity token is required to commit a record synchronously.")
        identity_token = IdentityToken(identity_token_str)

        # Construct DSSE Statement — subject uses chain_id format
        subject = Subject(
            name=f"trusted-log-chain_{chain_id}",
            digest={"sha384": event_digest.split(":")[1]}
        )
        statement = (
            StatementBuilder()
            .subjects([subject])
            .predicate_type("https://trusted-log.dev/v1")
            .predicate(predicate_payload)
            .build()
        )

        # Sign with Sigstore (Offline Mode)
        rekor_url = getattr(self.immutable_log, "rekor_url", None)
        ctx_prod = build_signing_context(rekor_url)
        
        bundle = None
        try:
            with ctx_prod.signer(identity_token, cache=True) as signer:
                bundle = signer.sign_dsse(statement)
        except Exception as e:
            logger.warning(f"Sigstore signing issue: {e}")
            raise

        bundle_json = bundle.to_json()
        
        # POST signed bundle to TruCon for sequencing
        trucon_response = self._post_to_trucon(
            bundle_json=bundle_json,
            chain_id=chain_id,
            event_digest=event_digest,
            event_id=event_id,
            intent_token=reservation.get("intent_token"),
            idempotency_key=idempotency_key,
            instance_id=instance_id,
            identity_token=identity_token_str,
        )

        # Clean up per-request scratch
        self._records.pop(record_id, None)
        self._entries.pop(record_id, None)
        
        return CommitResult(
            record_id=trucon_response.get("record_id", record_id),
            event_id=event_id,
            queue_status=SubmitStatus.PENDING,
            mr_value=trucon_response.get("mr_value"),
            prev_mr_value=trucon_response.get("prev_mr_value"),
        )

    def init_chain(self, chain_id: str = "default") -> Optional[Dict[str, Any]]:
        """
        Initialize a chain with Event Log 0 (baseline record).

        Two-phase protocol:
          1. GET /init-chain/{chain_id}/baseline → rtmr_value, ccel_digest, init_token
                    2. Build a Sigstore DSSE bundle for Event Log 0, POST /init-chain

        Returns the init-chain response dict on success, or None if the chain
        already exists (409) or TruCon is unreachable.
        """
        # Phase 1: Get baseline from TruCon
        try:
            baseline = request_json(
                "GET",
                f"/init-chain/{chain_id}/baseline",
                caller_service="tc_api",
                timeout=30,
                trucon_url=self._trucon_url,
            )
        except urllib.error.HTTPError as e:
            if e.code == 409:
                logger.info("Chain '%s' already initialized, skipping init-chain", chain_id)
                return None
            logger.warning("init-chain baseline failed for chain '%s': HTTP %d", chain_id, e.code)
            return None
        except urllib.error.URLError as e:
            logger.warning("TruCon unreachable for init-chain baseline: %s", e)
            return None

        init_token = baseline["init_token"]
        rtmr_value = baseline.get("rtmr_value")
        ccel_digest = baseline.get("ccel_digest")
        idempotency_key = f"init-chain-{chain_id}"

        try:
            intent = self._reserve_commit_intent(
                chain_id=chain_id,
                idempotency_key=idempotency_key,
                is_baseline=True,
            )
        except urllib.error.HTTPError as e:
            if e.code == 409:
                logger.info("Chain '%s' already initialized during baseline reservation, skipping", chain_id)
                return None
            logger.warning("init-chain reservation failed for chain '%s': HTTP %d", chain_id, e.code)
            return None
        except urllib.error.URLError as e:
            logger.warning("TruCon unreachable for init-chain reservation: %s", e)
            return None

        if intent.get("committed"):
            return {
                "record_id": intent.get("record_id"),
                "sequence_num": intent.get("sequence_num", 1),
            }

        try:
            signed_bundle, pub_key_pem, _event_digest = build_baseline_sigstore_bundle(
                chain_id=chain_id,
                rtmr_value=rtmr_value,
                ccel_digest=ccel_digest,
                rekor_url=getattr(self.immutable_log, "rekor_url", None),
                sequence_num=intent.get("sequence_num", 1),
                prev_event_digest=intent.get("prev_event_digest"),
                prev_lookup_hash=intent.get("prev_lookup_hash"),
            )
        except Exception as e:
            logger.warning("Failed to build baseline Sigstore bundle for chain '%s': %s", chain_id, e)
            return None

        # Phase 2: POST init-chain
        post_payload = {
            "chain_id": chain_id,
            "init_token": init_token,
            "intent_token": intent.get("intent_token"),
            "signed_bundle": signed_bundle,
            "pub_key": pub_key_pem,
        }

        try:
            result = request_json(
                "POST",
                "/init-chain",
                json_body=post_payload,
                caller_service="tc_api",
                timeout=30,
                trucon_url=self._trucon_url,
            )
            logger.info("Chain '%s' initialized: record_id=%s sequence_num=%d",
                        chain_id, result["record_id"], result["sequence_num"])
            return result
        except urllib.error.HTTPError as e:
            if e.code == 409:
                logger.info("Chain '%s' already initialized (race), skipping", chain_id)
                return None
            logger.warning("init-chain POST failed for chain '%s': HTTP %d", chain_id, e.code)
            return None
        except urllib.error.URLError as e:
            logger.warning("TruCon unreachable for init-chain POST: %s", e)
            return None

    def _reserve_commit_intent(
        self,
        chain_id: str,
        idempotency_key: Optional[str] = None,
        is_baseline: bool = False,
    ) -> Dict[str, Any]:
        payload = {
            "chain_id": chain_id,
            "idempotency_key": idempotency_key,
            "is_baseline": is_baseline,
        }
        return request_json(
            "POST",
            "/commit-intents/reserve",
            json_body=payload,
            caller_service="tc_api",
            timeout=30,
            trucon_url=self._trucon_url,
        )

    def _post_to_trucon(self, bundle_json: str, chain_id: str,
                            event_digest: str, event_id: str,
                            intent_token: Optional[str] = None,
                            idempotency_key: Optional[str] = None,
                            instance_id: Optional[str] = None,
                            identity_token: Optional[str] = None) -> Dict[str, Any]:
        """POST the signed bundle to TruCon /commit endpoint."""
        payload = {
            "bundle": bundle_json,
            "chain_id": chain_id,
            "event_digest": event_digest,
            "event_id": event_id,
            "intent_token": intent_token,
            "idempotency_key": idempotency_key,
            "instance_id": instance_id,
            "identity_token": identity_token,
        }
        try:
            return request_json(
                "POST",
                "/commit",
                json_body=payload,
                caller_service="tc_api",
                timeout=30,
                trucon_url=self._trucon_url,
            )
        except urllib.error.URLError as e:
            logger.error("TruCon unavailable via internal transport: %s", e)
            raise BackendSubmitError(
                f"TruCon sequencer unavailable: {e}",
                code="TRUCON_UNAVAILABLE",
                stage="commit",
                retryable=True,
            )

    def get_commit_queue_status(self, scope: Optional[str] = None) -> CommitQueueStatus:
        """Query TruCon for queue status."""
        try:
            data = request_json(
                "GET",
                "/status",
                caller_service="tc_api",
                timeout=10,
                trucon_url=self._trucon_url,
            )
            return CommitQueueStatus(
                has_queued_records=data.get("has_queued_records", False),
                queued_record_count=data.get("queued_record_count", 0),
                next_record_id=data.get("next_record_id"),
                total_retry_count=data.get("total_retry_count", 0),
            )
        except Exception as e:
            logger.warning("Could not reach TruCon for queue status: %s", e)
            return CommitQueueStatus(has_queued_records=False, queued_record_count=0)

    def verify_record(self, target: str, policy: Optional[Dict[str, Any]] = None) -> VerificationResult:
        """
        Verify a chain's entries by querying Rekor with chain_id subject name
        and filtering by signer identity. Optionally cross-check RTMR ordering.
        """
        applied_policy = policy or {}
        chain_id = applied_policy.get("chain_id", "default")
        expected_identity = applied_policy.get("signer_identity")
        expected_entry_count = applied_policy.get("expected_entry_count")
        subject_name = f"trusted-log-chain_{chain_id}"

        try:
            if not self.immutable_log:
                return VerificationResult(
                    success=False,
                    errors=["No immutable backend enabled."],
                    details={
                        "source": "immutable_backend",
                        "target": target,
                        "chain_id": chain_id,
                        "subject": subject_name,
                        "entries": [],
                    },
                )

            entries = self.immutable_log.traverse(target, count=100)

            if not entries:
                return VerificationResult(
                    success=False,
                    errors=[f"No entries found for {subject_name}"],
                    details={
                        "source": "immutable_backend",
                        "target": target,
                        "chain_id": chain_id,
                        "subject": subject_name,
                        "entries": [],
                        "observed_entry_count": 0,
                        "entry_count": 0,
                        "filtered_out_count": 0,
                        "applied_signer_identity": expected_identity,
                        "expected_entry_count": expected_entry_count,
                    },
                )

            normalized_entries = [
                _normalize_verification_entry(entry, index + 1, expected_identity)
                for index, entry in enumerate(entries)
            ]

            # Filter by signer identity if provided
            verified_entries = []
            for normalized_entry, raw_entry in zip(normalized_entries, entries):
                if expected_identity:
                    cert_identity = normalized_entry["signer_identity"]
                    if cert_identity and cert_identity != expected_identity:
                        logger.warning("Discarding entry with mismatched signer identity: %s", cert_identity)
                        continue
                verified_entries.append(raw_entry)

            if not verified_entries:
                return VerificationResult(
                    success=False,
                    errors=["No entries matched the expected signer identity"],
                    details={
                        "source": "immutable_backend",
                        "target": target,
                        "chain_id": chain_id,
                        "subject": subject_name,
                        "entries": normalized_entries,
                        "observed_entry_count": len(entries),
                        "entry_count": 0,
                        "filtered_out_count": len(entries),
                        "applied_signer_identity": expected_identity,
                        "expected_entry_count": expected_entry_count,
                    },
                )

            matched_entries = [entry for entry in normalized_entries if entry["included"]]
            matched_entries = _annotate_predecessor_verification(matched_entries, self.immutable_log)

            predecessor_errors = [
                entry for entry in matched_entries
                if entry.get("predecessor_ok") is False
            ]

            if predecessor_errors:
                return VerificationResult(
                    success=False,
                    errors=["Signed predecessor continuity verification failed"],
                    details={
                        "source": "immutable_backend",
                        "target": target,
                        "chain_id": chain_id,
                        "subject": subject_name,
                        "entries": matched_entries,
                        "observed_entry_count": len(entries),
                        "entry_count": len(matched_entries),
                        "filtered_out_count": len(entries) - len(matched_entries),
                        "applied_signer_identity": expected_identity,
                        "expected_entry_count": expected_entry_count,
                    },
                )

            if expected_entry_count is not None and len(matched_entries) != expected_entry_count:
                return VerificationResult(
                    success=False,
                    errors=[
                        f"Expected {expected_entry_count} entries, got {len(matched_entries)}"
                    ],
                    details={
                        "source": "immutable_backend",
                        "target": target,
                        "chain_id": chain_id,
                        "subject": subject_name,
                        "entries": matched_entries,
                        "observed_entry_count": len(entries),
                        "entry_count": len(matched_entries),
                        "filtered_out_count": len(entries) - len(matched_entries),
                        "applied_signer_identity": expected_identity,
                        "expected_entry_count": expected_entry_count,
                    },
                )

            return VerificationResult(
                success=True,
                details={
                    "source": "immutable_backend",
                    "target": target,
                    "chain_id": chain_id,
                    "entry_count": len(matched_entries),
                    "observed_entry_count": len(entries),
                    "filtered_out_count": len(entries) - len(matched_entries),
                    "applied_signer_identity": expected_identity,
                    "expected_entry_count": expected_entry_count,
                    "subject": subject_name,
                    "entries": matched_entries,
                },
            )
        except Exception as e:
            return VerificationResult(
                success=False,
                errors=[str(e)],
                details={
                    "source": "immutable_backend",
                    "target": target,
                    "chain_id": chain_id,
                    "subject": subject_name,
                    "entries": [],
                    "applied_signer_identity": expected_identity,
                    "expected_entry_count": expected_entry_count,
                },
            )


def _extract_signer_identity(entry: dict) -> Optional[str]:
    """Extract the Fulcio certificate identity from a Rekor log entry."""
    try:
        import base64
        body = entry.get("body", {})
        if isinstance(body, str):
            body = json.loads(base64.b64decode(body).decode("utf-8"))

        # Navigate to the certificate in DSSE/intoto-style entries.
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
    except Exception as e:
        logger.debug("Could not extract signer identity: %s", e)
    return None

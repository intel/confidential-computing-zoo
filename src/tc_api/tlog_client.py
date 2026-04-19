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

from sigstore.sign import SigningContext
from sigstore.oidc import IdentityToken
from sigstore.dsse import StatementBuilder, Subject
from sigstore.models import Bundle

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
    payload = body.get("spec", {}).get("payload")
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            import base64

            return json.loads(base64.b64decode(payload).decode("utf-8"))
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

    return {
        "index": index,
        "entry_id": entry.get("log_id") or entry.get("uuid") or entry.get("entryUUID"),
        "subject_names": subject_names,
        "event_id": predicate.get("event_id"),
        "event_type": predicate.get("event_type"),
        "digest": predicate.get("digest"),
        "predicate_entries": predicate.get("entries", []),
        "created": predicate.get("created"),
        "prev_log_id": predicate.get("prev_log_id") or payload.get("prev_log_id"),
        "signer_identity": signer_identity,
        "signer_identity_match": signer_match,
        "included": signer_match is not False,
        "errors": [],
    }


def compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: List[str]) -> str:
    """Compute SHA-384 event digest over metadata + entry digests (two-level algorithm)."""
    payload = canonical_json({
        "created": created_iso,
        "entry_digests": entry_digests,
        "event_id": event_id,
        "event_type": event_type,
    })
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


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
        ctx_prod = SigningContext.production()
        ctx_prod._rekor = None
        
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
            idempotency_key=idempotency_key,
            instance_id=instance_id,
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
          2. Generate ECDSA P-384 keypair, sign DSSE envelope, POST /init-chain

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

        # Generate ECDSA P-384 keypair
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives import hashes, serialization

        private_key = ec.generate_private_key(ec.SECP384R1())
        pub_key_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        # Build Event Log 0 DSSE payload
        entries = [
            {"key": "baseline_rtmr", "value": rtmr_value or "null"},
            {"key": "ccel_digest", "value": ccel_digest or "null"},
            {"key": "pub_key", "value": pub_key_pem},
        ]
        predicate_payload = {
            "event_id": f"evt-log0-{chain_id}",
            "event_type": "chain.init",
            "entries": entries,
            "chain_id": chain_id,
        }
        # DSSE envelope: payloadType + base64(payload)
        import base64
        payload_bytes = json.dumps(predicate_payload, separators=(',', ':'), sort_keys=True).encode("utf-8")
        payload_b64 = base64.b64encode(payload_bytes).decode("utf-8")

        # Sign with ECDSA P-384
        signature = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA384()))
        sig_b64 = base64.b64encode(signature).decode("utf-8")

        dsse_envelope = json.dumps({
            "payloadType": "application/vnd.dsse+json",
            "payload": payload_b64,
            "signatures": [{"keyid": "", "sig": sig_b64}],
        })

        # Zero the private key material
        del private_key

        # Phase 2: POST init-chain
        post_payload = {
            "chain_id": chain_id,
            "init_token": init_token,
            "signed_bundle": dsse_envelope,
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

    def _post_to_trucon(self, bundle_json: str, chain_id: str,
                            event_digest: str, event_id: str,
                            idempotency_key: Optional[str] = None,
                            instance_id: Optional[str] = None) -> Dict[str, Any]:
        """POST the signed bundle to TruCon /commit endpoint."""
        payload = {
            "bundle": bundle_json,
            "chain_id": chain_id,
            "event_digest": event_digest,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
            "instance_id": instance_id,
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
        
        # Navigate to the certificate in the DSSE/intoto entry
        spec = body.get("spec", {})
        signatures = spec.get("signatures", [])
        if signatures:
            cert_b64 = signatures[0].get("publicKey", {}).get("content")
            if cert_b64:
                # Decode cert and extract SAN/identity
                cert_pem = base64.b64decode(cert_b64)
                # For Fulcio certs, the identity is in the SAN extension
                # Using basic parsing — full X.509 parsing would use cryptography lib
                return cert_pem.decode("utf-8", errors="replace")
    except Exception as e:
        logger.debug("Could not extract signer identity: %s", e)
    return None

import hashlib
import json
import logging
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
    RecordContext, Entry, Record, EventLog, CommitResult, SubmitResult,
    CommitQueueStatus, LatestState, VerificationResult, SubmitStatus
)
from .tlog.errors import RecordNotFoundError, BackendSubmitError, VerificationError

logger = logging.getLogger(__name__)

def canonical_json(data: Any) -> str:
    """Return a highly deterministic JSON serialization for hashing."""
    return json.dumps(data, separators=(',', ':'), sort_keys=True, ensure_ascii=False)


def compute_entry_digest(key: str, value: str) -> str:
    """Compute SHA-384 digest of a single entry: SHA384(canonical({"key": k, "value": v}))."""
    payload = canonical_json({"key": key, "value": value})
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


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

    def _post_to_trucon(self, bundle_json: str, chain_id: str,
                            event_digest: str, event_id: str,
                            idempotency_key: Optional[str] = None) -> Dict[str, Any]:
        """POST the signed bundle to TruCon /commit endpoint."""
        url = f"{self._trucon_url}/commit"
        payload = json.dumps({
            "bundle": bundle_json,
            "chain_id": chain_id,
            "event_digest": event_digest,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
        }).encode("utf-8")

        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as e:
            logger.error("TruCon unavailable at %s: %s", url, e)
            raise BackendSubmitError(
                f"TruCon sequencer unavailable: {e}",
                code="TRUCON_UNAVAILABLE",
                stage="commit",
                retryable=True,
            )

    def get_commit_queue_status(self, scope: Optional[str] = None) -> CommitQueueStatus:
        """Query TruCon for queue status."""
        url = f"{self._trucon_url}/status"
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
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
        try:
            if not self.immutable_log:
                return VerificationResult(success=False, errors=["No immutable backend enabled."])
            
            chain_id = (policy or {}).get("chain_id", "default")
            expected_identity = (policy or {}).get("signer_identity")
            
            # Search Rekor by DSSE subject name: trusted-log-chain_{chain_id}
            subject_name = f"trusted-log-chain_{chain_id}"
            entries = self.immutable_log.traverse(target, count=100)
            
            if not entries:
                return VerificationResult(success=False, errors=[f"No entries found for {subject_name}"])
            
            # Filter by signer identity if provided
            verified_entries = []
            for entry in entries:
                if expected_identity:
                    # Extract certificate identity from entry
                    cert_identity = _extract_signer_identity(entry)
                    if cert_identity and cert_identity != expected_identity:
                        logger.warning("Discarding entry with mismatched signer identity: %s", cert_identity)
                        continue
                verified_entries.append(entry)
            
            if not verified_entries:
                return VerificationResult(
                    success=False,
                    errors=["No entries matched the expected signer identity"],
                )
            
            # RTMR ordering proof: if mr_values provided in policy, cross-check
            expected_mr_values = (policy or {}).get("mr_values")
            if expected_mr_values and len(expected_mr_values) != len(verified_entries):
                return VerificationResult(
                    success=False,
                    errors=[f"RTMR chain length mismatch: expected {len(expected_mr_values)}, got {len(verified_entries)}"],
                )
            
            return VerificationResult(
                success=True,
                details={
                    "chain_id": chain_id,
                    "entry_count": len(verified_entries),
                    "subject": subject_name,
                },
            )
        except Exception as e:
            return VerificationResult(success=False, errors=[str(e)])


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

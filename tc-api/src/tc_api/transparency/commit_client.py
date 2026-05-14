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
from sigstore.models import Bundle

from ..identity.sigstore_baseline import build_baseline_sigstore_bundle, build_signing_context
from ..identity.sigstore_baseline import get_chain_owner_private_key
from ..trucon.owner_authorization import verify_owner_authorization
from tlog.types import (
    RecordContext, Entry, Record, EventLog, CommitResult,
    CommitQueueStatus, LatestState, VerificationResult, SubmitStatus
)
from tlog.errors import RecordNotFoundError, BackendSubmitError, VerificationError
from ..trucon.database import get_chain_state
from ..trucon.internal_transport import request_json
from .trucon_submitter import post_commit_to_trucon, reserve_commit_intent

from tlog.digest import canonical_json
from .dsse_builder import attach_commit_context, build_event_predicate, build_statement

logger = logging.getLogger(__name__)


from .baseline import (
    _entry_has_required_history_fields,
    _entry_has_event_log0_baseline,
    _predicate_entry_value,
    _replay_owner_pub_key,
)
from .verification import (
    _annotate_delegation_verification,
    _annotate_owner_verification,
    _annotate_predecessor_verification,
    _decode_dsse_payload,
    _entry_matches_chain,
    _extract_signer_identity,
    _normalize_verification_entry,
)

try:
    from ..config import TRUCON_URL
except Exception:
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
        identity_token_str = (commit_options or {}).get("identity_token")
        if not identity_token_str:
            raise ValueError("Identity token is required to commit a record synchronously.")

        if get_chain_state(chain_id) is None:
            self.init_chain(chain_id, identity_token_str=identity_token_str)

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

        created_iso = event_log.created.isoformat()
        predicate_payload, event_digest = build_event_predicate(entries, event_id=event_log.event_id, event_type=event_log.event_type, created_iso=created_iso)
        event_log.digest = event_digest

        owner_private_key = get_chain_owner_private_key(chain_id)
        owner_authorization = attach_commit_context(
            predicate_payload,
            chain_id=chain_id,
            reservation=reservation,
            event_digest=event_digest,
            owner_private_key=owner_private_key,
        )
        
        identity_token = IdentityToken(identity_token_str)
        statement = build_statement(chain_id, event_digest, predicate_payload)

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
            owner_authorization=owner_authorization,
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

    def init_chain(
        self,
        chain_id: str = "default",
        identity_token_str: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Initialize a chain with Event Log 0 (baseline record).

        Two-phase protocol:
          1. GET /init-chain/{chain_id}/baseline → rtmr_value, ccel_digest, ccel_eventlog_b64, init_token
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
            raise RuntimeError(
                f"init-chain baseline failed for chain '{chain_id}': HTTP {e.code}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"TruCon unreachable for init-chain baseline on chain '{chain_id}': {e}"
            ) from e

        init_token = baseline["init_token"]
        rtmr_value = baseline.get("rtmr_value")
        ccel_digest = baseline.get("ccel_digest")
        ccel_eventlog_b64 = baseline.get("ccel_eventlog_b64")
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
            raise RuntimeError(
                f"init-chain reservation failed for chain '{chain_id}': HTTP {e.code}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"TruCon unreachable for init-chain reservation on chain '{chain_id}': {e}"
            ) from e

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
                ccel_eventlog_b64=ccel_eventlog_b64,
                identity_token_str=identity_token_str,
                rekor_url=getattr(self.immutable_log, "rekor_url", None),
                sequence_num=intent.get("sequence_num", 1),
                prev_event_digest=intent.get("prev_event_digest"),
                prev_lookup_hash=intent.get("prev_lookup_hash"),
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to build baseline Sigstore bundle for chain '{chain_id}': {e}"
            ) from e

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
            raise RuntimeError(
                f"init-chain POST failed for chain '{chain_id}': HTTP {e.code}"
            ) from e
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"TruCon unreachable for init-chain POST on chain '{chain_id}': {e}"
            ) from e

    def _reserve_commit_intent(
        self,
        chain_id: str,
        idempotency_key: Optional[str] = None,
        is_baseline: bool = False,
    ) -> Dict[str, Any]:
        return reserve_commit_intent(
            trucon_url=self._trucon_url,
            caller_service="tc_api",
            chain_id=chain_id,
            idempotency_key=idempotency_key,
            is_baseline=is_baseline,
        )

    def _post_to_trucon(self, bundle_json: str, chain_id: str,
                            event_digest: str, event_id: str,
                            intent_token: Optional[str] = None,
                            idempotency_key: Optional[str] = None,
                            instance_id: Optional[str] = None,
                            identity_token: Optional[str] = None,
                            owner_authorization: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST the signed bundle to TruCon /commit endpoint."""
        try:
            return post_commit_to_trucon(
                trucon_url=self._trucon_url,
                caller_service="tc_api",
                bundle_json=bundle_json,
                chain_id=chain_id,
                event_digest=event_digest,
                event_id=event_id,
                intent_token=intent_token,
                idempotency_key=idempotency_key,
                instance_id=instance_id,
                identity_token=identity_token,
                owner_authorization=owner_authorization,
            )
        except urllib.error.URLError as e:
            logger.error("TruCon unavailable via internal transport: %s", e)
            raise BackendSubmitError(
                code="TRUCON_UNAVAILABLE",
                message=f"TruCon sequencer unavailable: {e}",
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
        if self.immutable_log is not None:
            setattr(self.immutable_log, "require_mirror", bool(applied_policy.get("require_mirror")))
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

            # Filter replay results to the requested chain before applying signer constraints.
            matched_entries: List[Dict[str, Any]] = []
            for normalized_entry in normalized_entries:
                if not _entry_matches_chain(normalized_entry, chain_id, subject_name):
                    continue
                if expected_identity:
                    cert_identity = normalized_entry["signer_identity"]
                    # Allow delegation-authorized events (signer_identity is None
                    # because they are signed by owner key, not Fulcio)
                    if cert_identity and cert_identity != expected_identity:
                        logger.warning("Discarding entry with mismatched signer identity: %s", cert_identity)
                        continue
                matched_entries.append(normalized_entry)

            if not matched_entries:
                error_message = "No entries matched the expected signer identity"
                if expected_identity is None:
                    error_message = f"No entries matched the requested chain_id {chain_id!r}"
                return VerificationResult(
                    success=False,
                    errors=[error_message],
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

            matched_entries = _annotate_predecessor_verification(matched_entries, self.immutable_log)
            matched_entries = _annotate_owner_verification(matched_entries)
            matched_entries = _annotate_delegation_verification(matched_entries)

            predecessor_errors = [
                entry for entry in matched_entries
                if entry.get("predecessor_ok") is False
            ]
            owner_errors = [
                entry for entry in matched_entries
                if entry.get("owner_ok") is False
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

            if owner_errors:
                return VerificationResult(
                    success=False,
                    errors=["Owner authorization verification failed"],
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
__all__ = ["TrustedLogAPI"]

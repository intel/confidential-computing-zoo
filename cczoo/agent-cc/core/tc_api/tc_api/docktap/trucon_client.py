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

"""
Docktap TruCon commit client.

Submits signed DSSE bundles to TruCon for Docker lifecycle operations.
Failures are surfaced to the caller so the proxy can decide whether the
Docker response should still be released to the client.
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import urllib.request
import urllib.error

from tlog.types import Entry
from tc_api.identity.sigstore_identity import resolve_sigstore_identity_token
from tc_api.identity.sigstore_baseline import (
    build_baseline_sigstore_bundle,
    build_signing_context,
    generate_chain_owner_pub_key_pem,
    get_chain_owner_private_key,
    sign_dsse_with_owner_key,
)
from tc_api.trucon.internal_transport import request_json
from tc_api.trucon.database import update_commit_intent_status
from tc_api.transparency.events import runtime_operation_entries
from tc_api.transparency.dsse_builder import attach_commit_context, build_event_predicate, build_statement, build_statement_json
from tc_api.transparency.trucon_submitter import post_commit_to_trucon, reserve_commit_intent
from tlog.backends.rekor.adapter import SigstoreLogAdapter

from sigstore.oidc import IdentityToken, detect_credential
from sigstore.dsse import StatementBuilder, Subject

from . import config as _cfg

logger = logging.getLogger(__name__)

# Only these Docker operation types trigger a TruCon commit.
SUBMITTABLE_OPERATIONS = {"pull", "build", "create", "start", "stop", "rm"}
DEFAULT_RUNTIME_CHAIN_ID = _cfg.RUNTIME_CHAIN_ID


def _resolve_measured_chain_id(_chain_id: Optional[str] = None) -> str:
    return DEFAULT_RUNTIME_CHAIN_ID


def _resolve_identity_token_str() -> Optional[str]:
    """Resolve a Sigstore identity token for non-interactive Docktap use.

    Precedence:
    1. ``DOCKTAP_SIGSTORE_IDENTITY_TOKEN`` for sidecar-specific injection.
    2. ``SIGSTORE_IDENTITY_TOKEN`` for generic Sigstore-compatible tooling.
    3. Shared cached token resolution via ``tc_api.identity.sigstore_identity``.
    4. Ambient credential detection via ``sigstore.oidc.detect_credential()``.
    """
    for env_var in ("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", "SIGSTORE_IDENTITY_TOKEN"):
        token = os.environ.get(env_var, "").strip()
        if token:
            return token

    cached = resolve_sigstore_identity_token(
        operation="docktap",
        logger=logger,
        allow_interactive=False,
        require_token=False,
    )
    if cached:
        return cached

    detected = detect_credential()
    if not detected:
        return None

    token = str(detected).strip()
    return token or None


def has_reusable_identity_token() -> bool:
    return _resolve_identity_token_str() is not None


def has_active_delegation(chain_id: Optional[str] = None) -> bool:
    """Check if there is an active delegation for the given chain (or default runtime chain)."""
    from tc_api.trucon.database import get_active_delegation
    resolved_chain = _resolve_measured_chain_id(chain_id)
    try:
        return get_active_delegation(resolved_chain) is not None
    except Exception:
        return False


def _delegation_required() -> bool:
    return _cfg.delegation_required()


def _delegation_enabled() -> bool:
    return _cfg.delegation_enabled()


def _extract_rekor_identifiers(bundle) -> Dict[str, Optional[str]]:
    log_entry = getattr(bundle, "log_entry", None)
    if log_entry is None:
        return {"initial_bundle_rekor_uuid": None, "initial_bundle_rekor_log_index": None}

    rekor_uuid = getattr(log_entry, "uuid", None)
    rekor_log_index = getattr(log_entry, "log_index", None)
    return {
        "initial_bundle_rekor_uuid": str(rekor_uuid) if rekor_uuid else None,
        "initial_bundle_rekor_log_index": str(rekor_log_index) if rekor_log_index is not None else None,
    }


def _resolve_runtime_engine(op_record) -> str:
    runtime_engine = getattr(op_record, "runtime_engine", "")
    return runtime_engine or "docker"


@dataclass
class PendingSubmission:
    operation_type: str
    bundle_json: str
    chain_id: str
    event_digest: str
    event_id: str
    idempotency_key: str
    instance_id: Optional[str]
    intent_token: Optional[str] = None
    owner_authorization: Optional[Dict[str, object]] = None
    status: str = "retryable"
    retry_attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: Optional[str] = None
    record_id: Optional[str] = None
    sequence_num: Optional[int] = None
    resolved_at: Optional[float] = None
    op_record: Any = None
    workload_id: Optional[str] = None
    launch_id: Optional[str] = None


class RetryQueuedError(RuntimeError):
    """Raised after an initial retryable failure has been queued for retry."""


class MissingIdentityTokenError(RuntimeError):
    """Raised when Docktap cannot obtain a reusable Sigstore identity token."""


def _infer_operation_result(op_record) -> str:
    status_code = (op_record.response or {}).get("status")
    if isinstance(status_code, int):
        return "success" if 200 <= status_code < 400 else "failed"
    return "success"


def _build_entries(
    op_record,
    operation_type: str,
    *,
    workload_id: Optional[str] = None,
    launch_id: Optional[str] = None,
    instance_id: Optional[str] = None,
    operation_result: Optional[str] = None,
) -> List[Entry]:
    """Convert OperationRecord fields to Entry objects per operation type.

    Values are native Python objects (not JSON-encoded strings).
    Missing fields are omitted.
    """
    return runtime_operation_entries(
        operation_type,
        operation_result=operation_result or _infer_operation_result(op_record),
        runtime_engine=_resolve_runtime_engine(op_record),
        workload_id=workload_id,
        launch_id=launch_id,
        instance_id=instance_id,
        image=getattr(op_record, "image", {}),
        container=getattr(op_record, "container", {}),
    )


class TruConCommitter:
    """Lightweight client that signs and submits Docker operation events to TruCon."""

    def __init__(
        self,
        trucon_url: Optional[str] = None,
        workload_store=None,
        *,
        max_retry_attempts: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
        retry_poll_interval: float = 0.25,
        acknowledged_retention_hours: Optional[float] = None,
        terminal_retention_hours: Optional[float] = None,
        start_retry_worker: bool = True,
    ) -> None:
        self._trucon_url = trucon_url or _cfg.TRUCON_URL
        self._runtime_chain_id = _cfg.RUNTIME_CHAIN_ID
        self._workload_store = workload_store
        self._max_retry_attempts = max_retry_attempts if max_retry_attempts is not None else _cfg.TRUCON_MAX_RETRY_ATTEMPTS
        self._retry_base_delay = retry_base_delay if retry_base_delay is not None else _cfg.TRUCON_RETRY_BASE_DELAY
        self._retry_max_delay = retry_max_delay if retry_max_delay is not None else _cfg.TRUCON_RETRY_MAX_DELAY
        self._acknowledged_retention_hours = (
            acknowledged_retention_hours
            if acknowledged_retention_hours is not None
            else _cfg.ACKED_RETRY_RETENTION_HOURS
        )
        self._terminal_retention_hours = (
            terminal_retention_hours
            if terminal_retention_hours is not None
            else _cfg.TERMINAL_RETRY_RETENTION_HOURS
        )
        self._retry_poll_interval = retry_poll_interval
        self._retry_lock = threading.Lock()
        self._pending_submissions: Dict[str, PendingSubmission] = {}
        self._stop_retry_worker = threading.Event()
        self._retry_worker = None

        if start_retry_worker:
            self._retry_worker = threading.Thread(
                target=self._retry_loop,
                daemon=True,
                name="docktap-trucon-retry",
            )
            self._retry_worker.start()

    def submit_operation(self, op_record, operation_type: str, *, workload_id: Optional[str] = None, launch_id: Optional[str] = None) -> bool:
        """Submit a single Docker operation to TruCon as a signed DSSE bundle.

        *workload_id* is the value extracted from the ``io.trucon.workload-id``
        container label (only available for ``create`` operations).

        Returns True on success, False on failure.  Never raises.
        """
        try:
            return self._do_submit(op_record, operation_type, workload_id=workload_id, launch_id=launch_id)
        except Exception as exc:
            logger.warning(
                "TruCon commit failed for %s operation: %s", operation_type, exc
            )
            return False

    def shutdown(self) -> None:
        """Stop the background retry worker, if one is running."""
        self._stop_retry_worker.set()
        if self._retry_worker is not None:
            self._retry_worker.join(timeout=1.0)

    def process_retry_queue(self, now: Optional[float] = None) -> None:
        """Process all retryable submissions whose next attempt is due."""
        current_time = time.monotonic() if now is None else now
        with self._retry_lock:
            due_items = [
                submission
                for submission in self._pending_submissions.values()
                if submission.status == "queued"
                or (submission.status == "retryable" and submission.next_attempt_at <= current_time)
            ]

        for submission in due_items:
            if submission.status == "queued":
                self._process_queued_submission(submission)
                continue
            self._retry_submission(submission, current_time)

    def enqueue_operation(
        self,
        op_record,
        operation_type: str,
        *,
        workload_id: Optional[str] = None,
        launch_id: Optional[str] = None,
    ) -> str:
        """Queue a Docker lifecycle operation for asynchronous TruCon submission."""
        queue_event_id = f"queued-{uuid.uuid4().hex[:12]}"
        submission = PendingSubmission(
            operation_type=operation_type,
            bundle_json="",
            chain_id="",
            event_digest="",
            event_id=queue_event_id,
            idempotency_key=queue_event_id,
            instance_id=None,
            status="queued",
            op_record=op_record,
            workload_id=workload_id,
            launch_id=launch_id,
        )
        with self._retry_lock:
            self._pending_submissions[queue_event_id] = submission
        logger.info("Queued asynchronous TruCon submission for %s (queue_id=%s)", operation_type, queue_event_id)
        return queue_event_id

    def get_retry_snapshot(self) -> List[Dict[str, Optional[str]]]:
        """Return a serializable snapshot of local retry state for tests and diagnostics."""
        with self._retry_lock:
            items = list(self._pending_submissions.values())

        return [
            {
                "event_id": submission.event_id,
                "operation_type": submission.operation_type,
                "idempotency_key": submission.idempotency_key,
                "status": submission.status,
                "retry_attempts": submission.retry_attempts,
                "last_error": submission.last_error,
                "record_id": submission.record_id,
                "sequence_num": submission.sequence_num,
                "resolved_at": submission.resolved_at,
            }
            for submission in items
        ]

    def cleanup_resolved_submissions(self, now: Optional[float] = None) -> int:
        """Remove acknowledged or terminal retry records whose retention windows expired."""
        current_time = time.monotonic() if now is None else now
        ack_retention = self._acknowledged_retention_hours * 3600
        terminal_retention = self._terminal_retention_hours * 3600

        with self._retry_lock:
            expired_event_ids = []
            for event_id, submission in self._pending_submissions.items():
                if submission.status == "retryable":
                    continue
                if submission.resolved_at is None:
                    continue
                age_seconds = current_time - submission.resolved_at
                if submission.status == "acknowledged" and age_seconds >= ack_retention:
                    expired_event_ids.append(event_id)
                if submission.status == "failed_terminal" and age_seconds >= terminal_retention:
                    expired_event_ids.append(event_id)
            for event_id in expired_event_ids:
                self._pending_submissions.pop(event_id, None)
            return len(expired_event_ids)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_chain_id(self, op_record, operation_type: str, workload_id: Optional[str], launch_id: Optional[str] = None) -> str:
        """Determine chain_id for this operation."""
        if operation_type == "pull":
            return _resolve_measured_chain_id()

        container_id = op_record.container.get("id") if op_record.container else None

        if operation_type == "create":
            if workload_id:
                # Persist for future lookups
                if self._workload_store and container_id:
                    self._workload_store.put(container_id, workload_id, launch_id=launch_id, operation="create")
            return _resolve_measured_chain_id()
            
            return _resolve_measured_chain_id()

        # start / stop / rm — lookup persisted mapping
        if self._workload_store and container_id:
            stored = self._workload_store.get(container_id)
            if stored:
                self._workload_store.touch(container_id, operation_type)
                return _resolve_measured_chain_id(stored)
        return _resolve_measured_chain_id()

    def _resolve_submission_context(
        self,
        op_record,
        operation_type: str,
        workload_id: Optional[str],
        launch_id: Optional[str],
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        chain_id = self._resolve_chain_id(op_record, operation_type, workload_id, launch_id=launch_id)
        instance_id = None if operation_type == "pull" else (op_record.container.get("id") if op_record.container else None)
        resolved_workload_id = workload_id
        resolved_launch_id = launch_id

        if operation_type in ("start", "stop", "rm") and self._workload_store and instance_id:
            metadata = self._workload_store.get_metadata(instance_id)
            if metadata:
                resolved_workload_id = metadata.get("workload_id") or resolved_workload_id
                resolved_launch_id = metadata.get("launch_id") or resolved_launch_id

        return chain_id, resolved_workload_id, resolved_launch_id, instance_id

    def _retry_loop(self) -> None:
        while not self._stop_retry_worker.wait(self._retry_poll_interval):
            self.process_retry_queue()

    def _compute_backoff_delay(self, retry_attempts: int) -> float:
        delay = self._retry_base_delay * (2 ** max(retry_attempts - 1, 0))
        return min(delay, self._retry_max_delay)

    @staticmethod
    def _is_retryable_commit_error(exc: Exception) -> bool:
        if isinstance(exc, urllib.error.HTTPError):
            return exc.code >= 500
        return isinstance(exc, urllib.error.URLError)

    @staticmethod
    def _expire_intent(intent_token: Optional[str]) -> None:
        if not intent_token:
            return
        try:
            update_commit_intent_status(intent_token, "EXPIRED")
        except Exception:
            logger.warning("Failed to expire commit intent %s", intent_token, exc_info=True)

    def _mark_acknowledged(self, submission: PendingSubmission, response: Dict) -> None:
        with self._retry_lock:
            submission.status = "acknowledged"
            submission.last_error = None
            submission.record_id = response.get("record_id")
            submission.sequence_num = response.get("sequence_num")
            submission.resolved_at = time.monotonic()
            self._pending_submissions[submission.event_id] = submission

    def _mark_terminal(self, submission: PendingSubmission, error: Exception) -> None:
        self._expire_intent(submission.intent_token)
        with self._retry_lock:
            submission.status = "failed_terminal"
            submission.last_error = str(error)
            submission.resolved_at = time.monotonic()
            self._pending_submissions[submission.event_id] = submission

    def _queue_retry(self, submission: PendingSubmission, error: Exception) -> None:
        with self._retry_lock:
            submission.status = "retryable"
            submission.last_error = str(error)
            submission.resolved_at = None
            submission.next_attempt_at = time.monotonic() + self._compute_backoff_delay(submission.retry_attempts + 1)
            self._pending_submissions[submission.event_id] = submission

    def _retry_submission(self, submission: PendingSubmission, current_time: float) -> None:
        try:
            response = self._post_to_trucon(
                bundle_json=submission.bundle_json,
                chain_id=submission.chain_id,
                event_digest=submission.event_digest,
                event_id=submission.event_id,
                intent_token=submission.intent_token,
                idempotency_key=submission.idempotency_key,
                instance_id=submission.instance_id,
                owner_authorization=submission.owner_authorization,
            )
        except Exception as exc:
            if self._is_retryable_commit_error(exc):
                submission.retry_attempts += 1
                if submission.retry_attempts >= self._max_retry_attempts:
                    self._mark_terminal(submission, exc)
                    logger.warning(
                        "TruCon commit terminally failed for %s operation after %d retries: %s",
                        submission.operation_type,
                        submission.retry_attempts,
                        exc,
                    )
                    return

                submission.next_attempt_at = current_time + self._compute_backoff_delay(submission.retry_attempts + 1)
                submission.last_error = str(exc)
                with self._retry_lock:
                    self._pending_submissions[submission.event_id] = submission
                logger.warning(
                    "Retrying queued TruCon commit for %s operation (retry %d/%d): %s",
                    submission.operation_type,
                    submission.retry_attempts,
                    self._max_retry_attempts,
                    exc,
                )
                return

            self._mark_terminal(submission, exc)
            logger.warning(
                "TruCon commit terminally failed for %s operation with non-retryable error: %s",
                submission.operation_type,
                exc,
            )
            return

        self._mark_acknowledged(submission, response)
        logger.info(
            "TruCon commit acknowledged after retry for %s (event_id=%s)",
            submission.operation_type,
            submission.event_id,
        )

    def _process_queued_submission(self, submission: PendingSubmission) -> None:
        with self._retry_lock:
            current = self._pending_submissions.get(submission.event_id)
            if current is not submission:
                return

        try:
            self._do_submit(
                submission.op_record,
                submission.operation_type,
                workload_id=submission.workload_id,
                launch_id=submission.launch_id,
                pending_submission=submission,
            )
        except RetryQueuedError:
            with self._retry_lock:
                self._pending_submissions.pop(submission.event_id, None)
            logger.info(
                "Queued TruCon submission moved to retryable state for %s (queue_id=%s)",
                submission.operation_type,
                submission.event_id,
            )
        except Exception as exc:
            self._mark_terminal(submission, exc)
            logger.warning(
                "Queued TruCon submission terminally failed for %s (queue_id=%s): %s",
                submission.operation_type,
                submission.event_id,
                exc,
            )
        else:
            with self._retry_lock:
                self._pending_submissions.pop(submission.event_id, None)

    def _ensure_chain_initialized(self, chain_id: str, identity_token_str: str) -> Optional[Dict[str, object]]:
        chain_id = _resolve_measured_chain_id(chain_id)
        try:
            baseline = request_json(
                "GET",
                f"/init-chain/{chain_id}/baseline",
                caller_service="docktap",
                timeout=30,
                trucon_url=self._trucon_url,
            )
        except urllib.error.HTTPError as exc:
            if exc.code == 409:
                return None
            raise

        init_token = baseline["init_token"]
        rtmr_value = baseline.get("rtmr_value")
        ccel_digest = baseline.get("ccel_digest")
        ccel_eventlog_b64 = baseline.get("ccel_eventlog_b64")
        idempotency_key = f"init-chain-{chain_id}"

        reservation = self._reserve_commit_intent(
            chain_id=chain_id,
            idempotency_key=idempotency_key,
            is_baseline=True,
        )
        if reservation.get("committed"):
            return {
                "record_id": reservation.get("record_id"),
                "sequence_num": reservation.get("sequence_num", 1),
            }

        signed_bundle, pub_key_pem, _event_digest = build_baseline_sigstore_bundle(
            chain_id=chain_id,
            rtmr_value=rtmr_value,
            ccel_digest=ccel_digest,
            ccel_eventlog_b64=ccel_eventlog_b64,
            identity_token_str=identity_token_str,
            sequence_num=reservation.get("sequence_num", 1),
            prev_event_digest=reservation.get("prev_event_digest"),
            prev_lookup_hash=reservation.get("prev_lookup_hash"),
        )
        return request_json(
            "POST",
            "/init-chain",
            json_body={
                "chain_id": chain_id,
                "init_token": init_token,
                "intent_token": reservation.get("intent_token"),
                "signed_bundle": signed_bundle,
                "pub_key": pub_key_pem,
            },
            caller_service="docktap",
            timeout=30,
            trucon_url=self._trucon_url,
        )

    def _reserve_commit_intent(
        self,
        chain_id: str,
        idempotency_key: Optional[str] = None,
        is_baseline: bool = False,
    ) -> Dict[str, object]:
        chain_id = _resolve_measured_chain_id(chain_id)
        return reserve_commit_intent(
            trucon_url=self._trucon_url,
            caller_service="docktap",
            chain_id=chain_id,
            idempotency_key=idempotency_key,
            is_baseline=is_baseline,
        )

    def _do_submit(
        self,
        op_record,
        operation_type: str,
        *,
        workload_id: Optional[str] = None,
        launch_id: Optional[str] = None,
        pending_submission: Optional[PendingSubmission] = None,
    ) -> bool:
        chain_id, resolved_workload_id, resolved_launch_id, instance_id = self._resolve_submission_context(
            op_record,
            operation_type,
            workload_id,
            launch_id,
        )

        # 1. Build entries
        entry_list = _build_entries(
            op_record,
            operation_type,
            workload_id=resolved_workload_id,
            launch_id=resolved_launch_id,
            instance_id=instance_id,
        )

        event_id = f"evt-{uuid.uuid4().hex[:8]}"
        runtime_engine = _resolve_runtime_engine(op_record)
        event_type = f"{runtime_engine}_{operation_type}"
        predicate_payload, event_digest = build_event_predicate(entry_list, event_id=event_id, event_type=event_type)

        delegation = None
        if _delegation_enabled():
            from tc_api.trucon.database import get_active_delegation
            try:
                delegation = get_active_delegation(chain_id)
            except Exception:
                delegation = None

        if delegation is not None and operation_type not in delegation["scope"]:
            raise MissingIdentityTokenError(
                f"Active delegation does not include '{operation_type}' in scope"
            )

        # 4. Acquire authorization context based on the configured Docktap auth mode.
        identity_token_str = None if _delegation_required() else _resolve_identity_token_str()
        if _delegation_required():
            if delegation is None:
                raise MissingIdentityTokenError(
                    f"Active Docktap delegation is required for docker {operation_type}"
                )
        elif not identity_token_str:
            if delegation is None:
                raise MissingIdentityTokenError(
                    f"No reusable Sigstore identity token is available for docker {operation_type}"
                )

        if identity_token_str:
            self._ensure_chain_initialized(chain_id, identity_token_str)

        idempotency_key = f"idk-{uuid.uuid4().hex[:12]}"
        reservation = self._reserve_commit_intent(
            chain_id=chain_id,
            idempotency_key=idempotency_key,
        )
        if reservation.get("committed"):
            logger.info(
                "TruCon commit already recorded for %s (record_id=%s, sequence_num=%s)",
                operation_type,
                reservation.get("record_id"),
                reservation.get("sequence_num"),
            )
            return True

        if pending_submission is not None:
            pending_submission.chain_id = chain_id
            pending_submission.event_digest = event_digest
            pending_submission.idempotency_key = idempotency_key
            pending_submission.instance_id = instance_id
            pending_submission.intent_token = reservation.get("intent_token")

        try:
            owner_private_key = get_chain_owner_private_key(chain_id)
            owner_authorization = attach_commit_context(
                predicate_payload,
                chain_id=chain_id,
                reservation=reservation,
                event_digest=event_digest,
                owner_private_key=owner_private_key,
                delegation_id=delegation["delegation_id"] if delegation is not None else None,
            )

            statement_json = build_statement_json(chain_id, event_digest, predicate_payload)

            if delegation is not None and (_delegation_required() or not identity_token_str):
                # --- Owner key signing path (delegation active, no OIDC token) ---
                envelope = sign_dsse_with_owner_key(statement_json, owner_private_key)
                pub_key_pem = generate_chain_owner_pub_key_pem(chain_id)

                adapter = SigstoreLogAdapter()
                rekor_uuid, rekor_log_index, rekor_entry = adapter.submit_owner_signed_entry(
                    envelope, pub_key_pem,
                )

                bundle_json = json.dumps({
                    "_owner_key_signed": True,
                    "envelope": envelope,
                    "pub_key_pem": pub_key_pem,
                    "rekor_uuid": rekor_uuid,
                    "rekor_log_index": rekor_log_index,
                })
                rekor_identifiers = {
                    "initial_bundle_rekor_uuid": rekor_uuid,
                    "initial_bundle_rekor_log_index": rekor_log_index,
                }
            else:
                # --- Fulcio signing path (OIDC token available) ---
                identity_token = IdentityToken(identity_token_str)

                statement = build_statement(chain_id, event_digest, predicate_payload)

                signing_context = build_signing_context()
                with signing_context.signer(identity_token, cache=True) as signer:
                    bundle = signer.sign_dsse(statement)

                bundle_json = bundle.to_json()
                rekor_identifiers = _extract_rekor_identifiers(bundle)

            # 7. POST to TruCon /commit
            submission = PendingSubmission(
                operation_type=operation_type,
                bundle_json=bundle_json,
                chain_id=chain_id,
                event_digest=event_digest,
                event_id=event_id,
                idempotency_key=idempotency_key,
                instance_id=instance_id,
                intent_token=reservation.get("intent_token"),
                owner_authorization=owner_authorization,
            )

            if pending_submission is not None:
                pending_submission.bundle_json = bundle_json
                pending_submission.owner_authorization = owner_authorization

            try:
                response = self._post_to_trucon(
                    bundle_json=bundle_json,
                    chain_id=chain_id,
                    event_digest=event_digest,
                    event_id=event_id,
                    intent_token=reservation.get("intent_token"),
                    idempotency_key=idempotency_key,
                    instance_id=instance_id,
                    owner_authorization=owner_authorization,
                )
            except Exception as exc:
                if self._is_retryable_commit_error(exc):
                    self._queue_retry(submission, exc)
                    raise RetryQueuedError(str(exc)) from exc
                raise
        except RetryQueuedError:
            raise
        except Exception:
            if pending_submission is None:
                self._expire_intent(reservation.get("intent_token"))
            raise

        self._mark_acknowledged(submission, response)
        logger.info(
            "TruCon commit accepted for %s (event_id=%s, record_id=%s, sequence_num=%s, initial_bundle_rekor_uuid=%s, initial_bundle_rekor_log_index=%s)",
            operation_type,
            event_id,
            response.get("record_id"),
            response.get("sequence_num"),
            rekor_identifiers["initial_bundle_rekor_uuid"],
            rekor_identifiers["initial_bundle_rekor_log_index"],
        )
        return True

    def submit_delegation(
        self,
        chain_id: str,
        identity_token_str: str,
        scope: Optional[List[str]] = None,
        ttl_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a delegation chain event using the provided OIDC token.

        Returns dict with ``delegation_id`` and ``expires_at`` on success.
        Raises on failure.
        """
        from tc_api.docktap.delegation import build_delegation_predicate
        from tc_api.trucon.database import insert_delegation

        chain_id = _resolve_measured_chain_id(chain_id)
        self._ensure_chain_initialized(chain_id, identity_token_str)

        idempotency_key = f"idk-del-{uuid.uuid4().hex[:12]}"
        reservation = self._reserve_commit_intent(
            chain_id=chain_id,
            idempotency_key=idempotency_key,
        )
        if reservation.get("committed"):
            raise RuntimeError("Commit intent already fulfilled for delegation")

        predicate_payload, event_digest, delegation_id, expires_at = build_delegation_predicate(
            chain_id=chain_id,
            sequence_num=reservation["sequence_num"],
            prev_event_digest=reservation.get("prev_event_digest"),
            prev_lookup_hash=reservation.get("prev_lookup_hash"),
            scope=scope,
            ttl_seconds=ttl_seconds,
        )

        identity_token = IdentityToken(identity_token_str)
        signer_identity = identity_token.identity

        subject = Subject(
            name=f"trusted-log-chain_{chain_id}",
            digest={"sha384": event_digest.split(":")[1]},
        )
        statement = (
            StatementBuilder()
            .subjects([subject])
            .predicate_type("https://trusted-log.dev/v1")
            .predicate(predicate_payload)
            .build()
        )

        signing_context = build_signing_context()
        with signing_context.signer(identity_token, cache=True) as signer:
            bundle = signer.sign_dsse(statement)

        bundle_json = bundle.to_json()

        self._post_to_trucon(
            bundle_json=bundle_json,
            chain_id=chain_id,
            event_digest=event_digest,
            event_id=predicate_payload["event_id"],
            intent_token=reservation.get("intent_token"),
            idempotency_key=idempotency_key,
            instance_id=None,
            owner_authorization=predicate_payload.get("owner_authorization"),
        )

        resolved_scope = predicate_payload.get("scope", ["pull", "create", "start", "stop", "rm"])
        insert_delegation(
            delegation_id=delegation_id,
            chain_id=chain_id,
            scope=resolved_scope,
            expires_at=expires_at,
            signer_identity=signer_identity,
            sequence_num=reservation["sequence_num"],
        )

        logger.info(
            "Delegation created: delegation_id=%s, chain_id=%s, expires_at=%s, signer=%s",
            delegation_id,
            chain_id,
            expires_at,
            signer_identity,
        )

        return {
            "delegation_id": delegation_id,
            "expires_at": expires_at,
            "chain_id": chain_id,
            "scope": resolved_scope,
        }

    def _post_to_trucon(
        self,
        bundle_json: str,
        chain_id: str,
        event_digest: str,
        event_id: str,
        intent_token: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        instance_id: Optional[str] = None,
        owner_authorization: Optional[Dict[str, object]] = None,
    ) -> Dict:
        return post_commit_to_trucon(
            trucon_url=self._trucon_url,
            caller_service="docktap",
            bundle_json=bundle_json,
            chain_id=chain_id,
            event_digest=event_digest,
            event_id=event_id,
            intent_token=intent_token,
            idempotency_key=idempotency_key,
            instance_id=instance_id,
            owner_authorization=owner_authorization,
            timeout=5,
        )

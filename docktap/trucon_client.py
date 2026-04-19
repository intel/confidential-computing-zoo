"""
Docktap TruCon commit client.

Submits signed DSSE bundles to TruCon for Docker lifecycle operations.
Best-effort: failures are logged as warnings and never block Docker proxy
responses.
"""

import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import urllib.request
import urllib.error

from tc_api.tlog.types import Entry
from tc_api.tlog_client import (
    canonical_json,
    compute_entry_digest,
    compute_event_digest,
)

from sigstore.oidc import IdentityToken, detect_credential
from sigstore.sign import SigningContext
from sigstore.dsse import StatementBuilder, Subject

logger = logging.getLogger(__name__)

# Only these Docker operation types trigger a TruCon commit.
SUBMITTABLE_OPERATIONS = {"pull", "create", "start", "stop", "rm"}


@dataclass
class PendingSubmission:
    operation_type: str
    bundle_json: str
    chain_id: str
    event_digest: str
    event_id: str
    idempotency_key: str
    instance_id: Optional[str]
    status: str = "retryable"
    retry_attempts: int = 0
    next_attempt_at: float = 0.0
    last_error: Optional[str] = None
    record_id: Optional[str] = None
    sequence_num: Optional[int] = None
    resolved_at: Optional[float] = None


class RetryQueuedError(RuntimeError):
    """Raised after an initial retryable failure has been queued for retry."""


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
    entries: List[Entry] = []
    entries.append(Entry(key="operation_type", value=operation_type))
    entries.append(Entry(key="operation_result", value=operation_result or _infer_operation_result(op_record)))
    if workload_id:
        entries.append(Entry(key="workload_id", value=workload_id))
    if launch_id:
        entries.append(Entry(key="launch_id", value=launch_id))
    if instance_id:
        entries.append(Entry(key="instance_id", value=instance_id))

    if operation_type == "pull":
        if op_record.image.get("name"):
            entries.append(Entry(key="image_name", value=op_record.image["name"]))
        if op_record.image.get("tag"):
            entries.append(Entry(key="image_tag", value=op_record.image["tag"]))
        if op_record.image.get("digest"):
            entries.append(Entry(key="image_digest", value=op_record.image["digest"]))

    elif operation_type == "create":
        if op_record.image.get("name"):
            entries.append(Entry(key="image_name", value=op_record.image["name"]))
        if op_record.container.get("name"):
            entries.append(Entry(key="container_name", value=op_record.container["name"]))
        if op_record.container.get("id"):
            entries.append(Entry(key="container_id", value=op_record.container["id"]))

    elif operation_type in ("start", "stop", "rm"):
        if op_record.container.get("id"):
            entries.append(Entry(key="container_id", value=op_record.container["id"]))

    return entries


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
        self._trucon_url = trucon_url or os.environ.get(
            "TRUCON_URL", "http://127.0.0.1:8001"
        )
        self._workload_store = workload_store
        self._max_retry_attempts = max_retry_attempts if max_retry_attempts is not None else int(
            os.environ.get("DOCKTAP_TRUCON_MAX_RETRY_ATTEMPTS", "3")
        )
        self._retry_base_delay = retry_base_delay if retry_base_delay is not None else float(
            os.environ.get("DOCKTAP_TRUCON_RETRY_BASE_DELAY", "1.0")
        )
        self._retry_max_delay = retry_max_delay if retry_max_delay is not None else float(
            os.environ.get("DOCKTAP_TRUCON_RETRY_MAX_DELAY", "30.0")
        )
        self._acknowledged_retention_hours = (
            acknowledged_retention_hours
            if acknowledged_retention_hours is not None
            else float(os.environ.get("DOCKTAP_ACKED_RETRY_RETENTION_HOURS", "24"))
        )
        self._terminal_retention_hours = (
            terminal_retention_hours
            if terminal_retention_hours is not None
            else float(os.environ.get("DOCKTAP_TERMINAL_RETRY_RETENTION_HOURS", "168"))
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
                if submission.status == "retryable" and submission.next_attempt_at <= current_time
            ]

        for submission in due_items:
            self._retry_submission(submission, current_time)

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
            return "default"

        container_id = op_record.container.get("id") if op_record.container else None

        if operation_type == "create":
            if workload_id:
                # Persist for future lookups
                if self._workload_store and container_id:
                    self._workload_store.put(container_id, workload_id, launch_id=launch_id, operation="create")
                return workload_id
            return "default"

        # start / stop / rm — lookup persisted mapping
        if self._workload_store and container_id:
            stored = self._workload_store.get(container_id)
            if stored:
                self._workload_store.touch(container_id, operation_type)
                return stored
        return "default"

    def _resolve_submission_context(
        self,
        op_record,
        operation_type: str,
        workload_id: Optional[str],
        launch_id: Optional[str],
    ) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        chain_id = self._resolve_chain_id(op_record, operation_type, workload_id, launch_id=launch_id)
        instance_id = None if operation_type == "pull" else (op_record.container.get("id") if op_record.container else None)
        resolved_workload_id = workload_id or (chain_id if chain_id != "default" else None)
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

    def _mark_acknowledged(self, submission: PendingSubmission, response: Dict) -> None:
        with self._retry_lock:
            submission.status = "acknowledged"
            submission.last_error = None
            submission.record_id = response.get("record_id")
            submission.sequence_num = response.get("sequence_num")
            submission.resolved_at = time.monotonic()
            self._pending_submissions[submission.event_id] = submission

    def _mark_terminal(self, submission: PendingSubmission, error: Exception) -> None:
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
                idempotency_key=submission.idempotency_key,
                instance_id=submission.instance_id,
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

    def _do_submit(self, op_record, operation_type: str, *, workload_id: Optional[str] = None, launch_id: Optional[str] = None) -> bool:
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

        # 2. Compute digests (two-level algorithm)
        entry_digests = [compute_entry_digest(e.key, e.value) for e in entry_list]
        event_id = f"evt-{uuid.uuid4().hex[:8]}"
        event_type = f"docker_{operation_type}"
        created_iso = datetime.utcnow().isoformat()
        event_digest = compute_event_digest(event_id, event_type, created_iso, entry_digests)

        # 3. Build DSSE predicate
        predicate_payload = {
            "event_id": event_id,
            "event_type": event_type,
            "created": created_iso,
            "entries": [{"key": e.key, "value": e.value} for e in entry_list],
            "entry_digests": entry_digests,
            "digest": event_digest,
        }

        # 4. Acquire OIDC identity token
        identity_token_str = detect_credential()
        if not identity_token_str:
            logger.warning("No ambient OIDC credential available; skipping TruCon commit for %s", operation_type)
            return False

        identity_token = IdentityToken(identity_token_str)

        # 5. Build DSSE statement
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

        # 6. Sign with Sigstore (offline mode — no Rekor upload)
        ctx_prod = SigningContext.production()
        ctx_prod._rekor = None

        with ctx_prod.signer(identity_token, cache=True) as signer:
            bundle = signer.sign_dsse(statement)

        bundle_json = bundle.to_json()

        # 7. POST to TruCon /commit
        idempotency_key = f"idk-{uuid.uuid4().hex[:12]}"
        submission = PendingSubmission(
            operation_type=operation_type,
            bundle_json=bundle_json,
            chain_id=chain_id,
            event_digest=event_digest,
            event_id=event_id,
            idempotency_key=idempotency_key,
            instance_id=instance_id,
        )

        try:
            response = self._post_to_trucon(
                bundle_json=bundle_json,
                chain_id=chain_id,
                event_digest=event_digest,
                event_id=event_id,
                idempotency_key=idempotency_key,
                instance_id=instance_id,
            )
        except Exception as exc:
            if self._is_retryable_commit_error(exc):
                self._queue_retry(submission, exc)
                raise RetryQueuedError(str(exc)) from exc
            raise

        self._mark_acknowledged(submission, response)
        logger.info("TruCon commit succeeded for %s (event_id=%s)", operation_type, event_id)
        return True

    def _post_to_trucon(
        self,
        bundle_json: str,
        chain_id: str,
        event_digest: str,
        event_id: str,
        idempotency_key: Optional[str] = None,
        instance_id: Optional[str] = None,
    ) -> Dict:
        url = f"{self._trucon_url}/commit"
        payload = json.dumps({
            "bundle": bundle_json,
            "chain_id": chain_id,
            "event_digest": event_digest,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
            "instance_id": instance_id,
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        service_token = os.environ.get("TRUCON_SERVICE_TOKEN", "")
        if service_token:
            headers["Authorization"] = f"Bearer {service_token}"

        req = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))

"""
Docktap TruCon commit client.

Submits signed DSSE bundles to TruCon for Docker lifecycle operations.
Best-effort: failures are logged as warnings and never block Docker proxy
responses.
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import urllib.request
import urllib.error

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


def _build_entries(op_record, operation_type: str) -> List[Tuple[str, str]]:
    """Convert OperationRecord fields to (key, value) pairs per operation type.

    Values are JSON-encoded strings consistent with tc_api convention.
    Missing fields are omitted.
    """
    entries: List[Tuple[str, str]] = []
    entries.append(("operation_type", json.dumps(operation_type)))

    if operation_type == "pull":
        if op_record.image.get("name"):
            entries.append(("image_name", json.dumps(op_record.image["name"])))
        if op_record.image.get("tag"):
            entries.append(("image_tag", json.dumps(op_record.image["tag"])))
        if op_record.image.get("digest"):
            entries.append(("image_digest", json.dumps(op_record.image["digest"])))

    elif operation_type == "create":
        if op_record.image.get("name"):
            entries.append(("image_name", json.dumps(op_record.image["name"])))
        if op_record.container.get("name"):
            entries.append(("container_name", json.dumps(op_record.container["name"])))
        if op_record.container.get("id"):
            entries.append(("container_id", json.dumps(op_record.container["id"])))

    elif operation_type in ("start", "stop", "rm"):
        if op_record.container.get("id"):
            entries.append(("container_id", json.dumps(op_record.container["id"])))

    return entries


class TruConCommitter:
    """Lightweight client that signs and submits Docker operation events to TruCon."""

    def __init__(self, trucon_url: Optional[str] = None, workload_store=None) -> None:
        self._trucon_url = trucon_url or os.environ.get(
            "TRUCON_URL", "http://127.0.0.1:8001"
        )
        self._workload_store = workload_store

    def submit_operation(self, op_record, operation_type: str, *, workload_id: Optional[str] = None) -> bool:
        """Submit a single Docker operation to TruCon as a signed DSSE bundle.

        *workload_id* is the value extracted from the ``io.trucon.workload-id``
        container label (only available for ``create`` operations).

        Returns True on success, False on failure.  Never raises.
        """
        try:
            return self._do_submit(op_record, operation_type, workload_id=workload_id)
        except Exception as exc:
            logger.warning(
                "TruCon commit failed for %s operation: %s", operation_type, exc
            )
            return False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_chain_id(self, op_record, operation_type: str, workload_id: Optional[str]) -> str:
        """Determine chain_id for this operation."""
        if operation_type == "pull":
            return "default"

        container_id = op_record.container.get("id") if op_record.container else None

        if operation_type == "create":
            if workload_id:
                # Persist for future lookups
                if self._workload_store and container_id:
                    self._workload_store.put(container_id, workload_id)
                return workload_id
            return "default"

        # start / stop / rm — lookup persisted mapping
        if self._workload_store and container_id:
            stored = self._workload_store.get(container_id)
            if stored:
                return stored
        return "default"

    def _do_submit(self, op_record, operation_type: str, *, workload_id: Optional[str] = None) -> bool:
        # 1. Build entries
        entry_pairs = _build_entries(op_record, operation_type)

        # 2. Compute digests (two-level algorithm)
        entry_digests = [compute_entry_digest(k, v) for k, v in entry_pairs]
        event_id = f"evt-{uuid.uuid4().hex[:8]}"
        event_type = f"docker_{operation_type}"
        created_iso = datetime.utcnow().isoformat()
        event_digest = compute_event_digest(event_id, event_type, created_iso, entry_digests)

        # 3. Build DSSE predicate
        chain_id = self._resolve_chain_id(op_record, operation_type, workload_id)
        predicate_payload = {
            "event_id": event_id,
            "event_type": event_type,
            "created": created_iso,
            "entries": [{"key": k, "value": v} for k, v in entry_pairs],
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
        self._post_to_trucon(
            bundle_json=bundle_json,
            chain_id=chain_id,
            event_digest=event_digest,
            event_id=event_id,
            idempotency_key=idempotency_key,
        )
        logger.info("TruCon commit succeeded for %s (event_id=%s)", operation_type, event_id)
        return True

    def _post_to_trucon(
        self,
        bundle_json: str,
        chain_id: str,
        event_digest: str,
        event_id: str,
        idempotency_key: Optional[str] = None,
    ) -> Dict:
        url = f"{self._trucon_url}/commit"
        payload = json.dumps({
            "bundle": bundle_json,
            "chain_id": chain_id,
            "event_digest": event_digest,
            "event_id": event_id,
            "idempotency_key": idempotency_key,
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

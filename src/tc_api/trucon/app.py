"""
TruCon — Single-instance sequencer for the Trusted Container Log.

Serializes RTMR extend + SQLite INSERT behind a threading.Lock(),
maintains chain state, and embeds a submit daemon as a background thread.

MUST be run with --workers 1 to preserve lock semantics.
"""

import fcntl
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sigstore.models import Bundle

from .database import (
    DB_PATH,
    create_commit_intent,
    delete_non_extended_records,
    enqueue_mirror_publish,
    expire_active_commit_intents,
    get_active_commit_intent_for_chain,
    get_all_chain_ids,
    get_chain_records,
    get_chain_state,
    get_commit_intent_by_idempotency_key,
    get_commit_intent_by_token,
    get_db_connection,
    get_events_for_instance,
    get_events_for_workload,
    get_failed_by_chain,
    get_highest_extended_record,
    get_instances_for_workload,
    get_latest_confirmed_record,
    get_latest_state,
    get_mirror_publish_job,
    get_pending_mirror_publishes,
    get_pending_by_chain,
    get_queue_stats,
    get_record_by_id,
    get_record_by_idempotency_key,
    increment_retry,
    init_db,
    insert_record,
    reset_submitting_to_pending,
    set_status_submitting,
    update_commit_intent_status,
    update_chain_state,
    update_mirror_publish_status,
    update_record_confirmed,
    update_status,
)
from tc_api.sigstore_baseline import build_baseline_sigstore_bundle
from .adapters.oci_mirror import OciBundleMirror, build_mirror_annotations
from .adapters.sigstore import SigstoreLogAdapter
from .adapters.ccel import compute_ccel_digest, read_ccel_eventlog_b64
from .adapters.tdx_quote import TdxQuoteAdapter
from .internal_transport import (
    AUTH_TRANSPORT_HEADER,
    CALLER_SERVICE_HEADER,
    INTERNAL_PROXY_SECRET_HEADER,
    PEER_GID_HEADER,
    PEER_PID_HEADER,
    PEER_UID_HEADER,
)
from .uds_gateway import TruConUnixSocketGateway
from .evidence import (
    AttestedHeadEvidence,
    BINDING_ALGORITHM,
    REQUIRED_BOUND_FIELDS,
    compute_binding_expected_value,
    validate_attested_head_evidence_payload,
)
from .owner_attestation import (
    OWNER_BINDING_ALGORITHM,
    REQUIRED_OWNER_BOUND_FIELDS,
    compute_owner_attestation_expected_value,
    validate_chain_root_owner_attestation_payload,
)
from .owner_authorization import verify_owner_authorization

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("trucon")

INTENT_TTL_SECONDS = int(os.environ.get("TRUCON_INTENT_TTL_SECONDS", "300"))


def _extract_confirmed_rekor_identifiers(log_id: str, receipt: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    receipt_data = receipt or {}
    confirmed_rekor_uuid = receipt_data.get("uuid") or receipt_data.get("entryUUID")
    confirmed_rekor_log_index = receipt_data.get("log_index") or receipt_data.get("logIndex")
    confirmed_rekor_log_id = receipt_data.get("log_id") or receipt_data.get("logID") or log_id
    return {
        "confirmed_rekor_log_id": str(confirmed_rekor_log_id) if confirmed_rekor_log_id is not None else None,
        "confirmed_rekor_uuid": str(confirmed_rekor_uuid) if confirmed_rekor_uuid else None,
        "confirmed_rekor_log_index": str(confirmed_rekor_log_index) if confirmed_rekor_log_index is not None else None,
    }


def _build_chain_owner_attestation(
    chain_id: str,
    sequence_num: int,
    baseline_rtmr: Optional[str],
    ccel_digest: Optional[str],
    owner_pub_key: str,
) -> Dict[str, Any]:
    if _quote_adapter is None:
        raise HTTPException(status_code=500, detail="Quote adapter is unavailable")

    expected_value = compute_owner_attestation_expected_value(
        chain_id=chain_id,
        sequence_num=sequence_num,
        baseline_rtmr=baseline_rtmr,
        ccel_digest=ccel_digest,
        owner_pub_key=owner_pub_key,
    )

    try:
        quote_material = _quote_adapter.quote(expected_value)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Owner attestation quote acquisition failed: {exc}") from exc

    if quote_material.report_data != expected_value:
        raise HTTPException(status_code=500, detail="Owner attestation report data did not match the expected binding value")

    return validate_chain_root_owner_attestation_payload(
        {
            "version": "v1",
            "tee_type": "tdx",
            "chain_id": chain_id,
            "sequence_num": sequence_num,
            "owner_pub_key": owner_pub_key,
            "baseline_rtmr": baseline_rtmr,
            "ccel_digest": ccel_digest,
            "generated_at": datetime.utcnow(),
            "quote": quote_material.quote,
            "quote_format": quote_material.quote_format,
            "report_data_binding": {
                "algorithm": OWNER_BINDING_ALGORITHM,
                "bound_fields": list(REQUIRED_OWNER_BOUND_FIELDS),
                "expected_value": expected_value,
            },
        }
    ).model_dump(mode="json")


def _extract_bundle_payload(bundle_json: str) -> Dict[str, Any]:
    bundle = Bundle.from_json(bundle_json)
    envelope = bundle._dsse_envelope
    if envelope is None:
        raise ValueError("Bundle does not contain a DSSE envelope")
    envelope_json = json.loads(envelope.to_json())
    payload_b64 = envelope_json.get("payload")
    if not isinstance(payload_b64, str):
        raise ValueError("Bundle DSSE envelope is missing payload")
    return json.loads(base64.b64decode(payload_b64).decode("utf-8"))


def _extract_bundle_predicate(bundle_json: str) -> Dict[str, Any]:
    payload = _extract_bundle_payload(bundle_json)
    predicate = payload.get("predicate")
    if not isinstance(predicate, dict):
        raise ValueError("Bundle DSSE payload is missing predicate")
    return predicate


def _compute_bundle_payload_hash(bundle_json: str) -> str:
    bundle = Bundle.from_json(bundle_json)
    envelope = bundle._dsse_envelope
    if envelope is None:
        raise ValueError("Bundle does not contain a DSSE envelope")
    envelope_json = json.loads(envelope.to_json())
    payload_b64 = envelope_json.get("payload")
    if not isinstance(payload_b64, str):
        raise ValueError("Bundle DSSE envelope is missing payload")
    payload_bytes = base64.b64decode(payload_b64)
    return "sha256:" + hashlib.sha256(payload_bytes).hexdigest()


def _compute_record_lookup_hash(record: Any) -> Optional[str]:
    payload = record["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    if not isinstance(payload, dict):
        return None
    bundle_json = payload.get("bundle")
    if not isinstance(bundle_json, str):
        return None
    try:
        return _compute_bundle_payload_hash(bundle_json)
    except Exception:
        return None


def _intent_expired(intent: Any) -> bool:
    expires_at = intent["expires_at"] if intent and "expires_at" in intent.keys() else None
    return isinstance(expires_at, str) and expires_at < datetime.utcnow().isoformat()


def _intent_response_from_row(intent: Any, committed_record: Optional[Any] = None) -> Dict[str, Any]:
    response = {
        "intent_token": intent["intent_token"],
        "chain_id": intent["chain_id"],
        "sequence_num": intent["sequence_num"],
        "prev_event_digest": intent["prev_event_digest"],
        "prev_lookup_hash": intent["prev_lookup_hash"],
        "expires_at": intent["expires_at"],
        "committed": False,
        "record_id": None,
    }
    if committed_record is not None:
        response["committed"] = True
        response["record_id"] = committed_record["record_id"]
        response["sequence_num"] = committed_record["sequence_num"]
    return response


def _create_workload_chain_baseline(
    chain_id: str,
    caller_service: Optional[str],
    auth_transport: Optional[str],
    identity_token_str: Optional[str] = None,
) -> None:
    """Create Event Log 0 for a previously unseen non-default chain."""
    if chain_id == "default" or get_chain_state(chain_id):
        return

    rtmr_value = None
    if _local_mr:
        try:
            rtmr_value = _local_mr.read(RTMR_INDEX)
        except Exception as exc:
            logger.error("Failed to read RTMR[%d] for lazy baseline on chain '%s': %s", RTMR_INDEX, chain_id, exc)
            raise HTTPException(status_code=500, detail=f"Baseline creation failed: {exc}") from exc

    try:
        ccel_digest = compute_ccel_digest()
        ccel_eventlog_b64 = read_ccel_eventlog_b64()
        signed_bundle, pub_key_pem, event_digest = build_baseline_sigstore_bundle(
            chain_id=chain_id,
            rtmr_value=rtmr_value,
            ccel_digest=ccel_digest,
            ccel_eventlog_b64=ccel_eventlog_b64,
            identity_token_str=identity_token_str,
            rekor_url=getattr(_immutable_log, "rekor_url", None),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to construct lazy baseline bundle for chain '%s': %s", chain_id, exc)
        raise HTTPException(status_code=500, detail=f"Baseline creation failed: {exc}") from exc

    record_id = str(uuid.uuid4())
    owner_attestation = _build_chain_owner_attestation(
        chain_id=chain_id,
        sequence_num=1,
        baseline_rtmr=rtmr_value,
        ccel_digest=ccel_digest,
        owner_pub_key=pub_key_pem,
    )
    insert_record(
        record_id=record_id,
        event_id=f"evt-log0-{chain_id}",
        payload={
            "bundle": signed_bundle,
            "chain_id": chain_id,
            "pub_key": pub_key_pem,
            "owner_attestation": owner_attestation,
            "is_baseline": True,
            "caller_service": caller_service,
            "auth_transport": auth_transport,
        },
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        prev_log_id=None,
        mr_value=rtmr_value,
        sequence_num=1,
        event_digest=event_digest,
        idempotency_key=f"init-chain-{chain_id}",
        instance_id=None,
    )
    update_chain_state(
        chain_id=chain_id,
        head_record_id=record_id,
        sequence_num=1,
        mr_value=rtmr_value,
    )
    logger.info(
        "Auto-created workload baseline for chain '%s' record_id=%s caller_service=%s auth_transport=%s",
        chain_id,
        record_id,
        caller_service,
        auth_transport,
    )


def _record_is_baseline(record: Any) -> bool:
    payload = record["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return False
    return isinstance(payload, dict) and bool(payload.get("is_baseline"))


def _record_payload_dict(record: Any) -> Optional[Dict[str, Any]]:
    payload = record["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def _get_chain_owner_pub_key_from_records(records: list[Any]) -> Optional[str]:
    if not records:
        return None

    baseline = records[0]
    if not _record_is_baseline(baseline):
        return None

    payload = _record_payload_dict(baseline)
    if payload is None:
        return None
    if not isinstance(payload.get("owner_attestation"), dict):
        return None
    owner_pub_key = payload.get("pub_key")
    return owner_pub_key if isinstance(owner_pub_key, str) and owner_pub_key else None


def _get_chain_owner_pub_key(chain_id: str) -> Optional[str]:
    return _get_chain_owner_pub_key_from_records(get_chain_records(chain_id))

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CommitRequest(BaseModel):
    bundle: str          # Signed DSSE bundle JSON string
    chain_id: str        # Chain identifier
    event_digest: str    # SHA-384 digest of the event
    event_id: Optional[str] = None
    intent_token: Optional[str] = None
    idempotency_key: Optional[str] = None
    instance_id: Optional[str] = None
    identity_token: Optional[str] = None
    owner_authorization: Optional[Dict[str, Any]] = None

class CommitResponse(BaseModel):
    record_id: str
    sequence_num: int
    mr_value: Optional[str] = None
    prev_mr_value: Optional[str] = None

class ChainStateResponse(BaseModel):
    chain_id: str
    head_record_id: Optional[str] = None
    head_log_id: Optional[str] = None
    sequence_num: int = 0
    mr_value: Optional[str] = None
    updated_at: Optional[str] = None

class CommitQueueStatusResponse(BaseModel):
    has_queued_records: bool
    queued_record_count: int
    next_record_id: Optional[str] = None
    submitting_count: int = 0
    failed_retryable_count: int = 0
    failed_terminal_count: int = 0
    total_retry_count: int = 0

class LatestStateResponse(BaseModel):
    latest_confirmed_log_id: Optional[str] = None
    pending_record_count: int = 0
    pending_event_ids: List[str] = []
    latest_mr_value: Optional[str] = None

class InitChainBaselineResponse(BaseModel):
    rtmr_value: Optional[str] = None
    ccel_digest: Optional[str] = None
    ccel_eventlog_b64: Optional[str] = None
    init_token: str

class InitChainRequest(BaseModel):
    chain_id: str
    init_token: str
    intent_token: str
    signed_bundle: str   # Sigstore Bundle JSON for the explicit baseline record
    pub_key: str         # ECDSA P-384 public key in PEM format


class CommitIntentReserveRequest(BaseModel):
    chain_id: str
    idempotency_key: Optional[str] = None
    is_baseline: bool = False


class CommitIntentReserveResponse(BaseModel):
    intent_token: Optional[str] = None
    chain_id: str
    sequence_num: int
    prev_event_digest: Optional[str] = None
    prev_lookup_hash: Optional[str] = None
    expires_at: Optional[str] = None
    committed: bool = False
    record_id: Optional[str] = None

class InitChainResponse(BaseModel):
    record_id: str
    sequence_num: int

class ChainEntryResult(BaseModel):
    seq: int
    record_id: str
    event_id: Optional[str] = None
    mr_ok: Optional[bool] = None
    rekor_ok: bool
    rtmr_extended: bool
    mr_value: Optional[str] = None
    predecessor_ok: Optional[bool] = None
    predecessor_status: Optional[str] = None
    owner_ok: Optional[bool] = None
    owner_status: Optional[str] = None
    prev_event_digest: Optional[str] = None
    prev_lookup_hash: Optional[str] = None
    candidate_count: Optional[int] = None
    materialized_candidate_count: Optional[int] = None
    matched_candidate_count: Optional[int] = None
    boundary_status: Optional[str] = None
    error: Optional[str] = None

class ChainVerificationResponse(BaseModel):
    valid: bool
    chain_id: str
    total_entries: int
    mr_verified: int
    rekor_confirmed: int
    rekor_pending: int
    rtmr_available: bool
    head_mr_value: Optional[str] = None
    first_error_at: Optional[int] = None
    entries: list[ChainEntryResult]

class InstanceSummary(BaseModel):
    instance_id: str
    first_event_at: Optional[str] = None
    last_event_at: Optional[str] = None
    event_count: int

class EventSummary(BaseModel):
    record_id: str
    event_id: Optional[str] = None
    sequence_num: int
    status: str
    created_at: Optional[str] = None
    instance_id: Optional[str] = None


class EvidenceErrorResponse(BaseModel):
    detail: str

# ---------------------------------------------------------------------------
# Single-instance file lock
# ---------------------------------------------------------------------------

LOCK_PATH = "/dev/shm/tc_api_queue/trucon.lock"
_lock_fd = None

def acquire_instance_lock():
    """Acquire exclusive file lock. Exits if another instance holds it."""
    global _lock_fd
    lock_dir = os.path.dirname(LOCK_PATH)
    os.makedirs(lock_dir, mode=0o700, exist_ok=True)
    try:
        _lock_fd = open(LOCK_PATH, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        logger.info("Acquired single-instance lock at %s (PID %d)", LOCK_PATH, os.getpid())
    except OSError:
        logger.error("Another TruCon instance is already running (lock held at %s)", LOCK_PATH)
        sys.exit(1)

def release_instance_lock():
    global _lock_fd
    if _lock_fd:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
            _lock_fd.close()
        except Exception:
            pass
        _lock_fd = None

# ---------------------------------------------------------------------------
# Sequencer lock + local MR adapter
# ---------------------------------------------------------------------------

_sequencer_lock = threading.Lock()
_local_mr = None       # Set during lifespan
_immutable_log = None   # Set during lifespan
_quote_adapter = None    # Set during lifespan

# RTMR[2] is the default OS/application-layer measurement register in TDX.
# RTMR[0]/[1] are firmware/boot-locked; RTMR[3] can be used for experiments.
RTMR_INDEX = int(os.environ.get("TRUCON_RTMR_INDEX", "2"))

# Pending init tokens: {init_token -> chain_id}
# Populated by GET /init-chain/.../baseline, consumed by POST /init-chain
_pending_init_tokens: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

def _crash_recovery():
    """Run on startup: discard non-extended records, reset SUBMITTING, rebuild chain_state."""
    deleted = delete_non_extended_records()
    if deleted:
        logger.info("Crash recovery: deleted %d records without RTMR extension", deleted)

    expired = expire_active_commit_intents()
    if expired:
        logger.info("Crash recovery: expired %d stale commit intents", expired)

    # Reset any SUBMITTING records back to PENDING (interrupted submission)
    reset_count = reset_submitting_to_pending()
    if reset_count:
        logger.info("Crash recovery: reset %d SUBMITTING records to PENDING", reset_count)

    # Rebuild chain_state from surviving records
    chain_ids = get_all_chain_ids()
    for cid in chain_ids:
        highest = get_highest_extended_record(cid)
        if highest:
            update_chain_state(
                chain_id=cid,
                head_record_id=highest['record_id'],
                sequence_num=highest['sequence_num'],
                mr_value=highest['mr_value'],
            )
            logger.info("Rebuilt chain_state for chain '%s' at sequence_num=%d", cid, highest['sequence_num'])


def _initialize_local_mr_adapter():
    from .adapters.tdx_mr import TdxMRAdapter

    if TdxMRAdapter.is_available(RTMR_INDEX):
        logger.info("TDX RTMR adapter initialized")
        return TdxMRAdapter()

    if TdxMRAdapter.is_extend_available(RTMR_INDEX):
        logger.info("TDX RTMR adapter initialized via libtdx_attest fallback")
        return TdxMRAdapter()

    if TdxMRAdapter.is_report_read_available(RTMR_INDEX):
        message = (
            "TDX RTMR sysfs not found, but TDREPORT-backed RTMR reads are available; "
            "no RTMR extend interface is available on this platform"
        )
        if _ENABLE_TDX:
            logger.error("ENABLE_TDX=true but %s. Refusing to start in degraded mode.", message)
            raise RuntimeError(f"ENABLE_TDX=true requires RTMR extend support; {message}")
        logger.warning(
            "NON-TEE MODE: %s; running without hardware measurement extensions because no extend interface is available on this platform",
            message,
        )
        return None

    message = "TDX RTMR sysfs not found and no libtdx_attest extend path is available"
    if _ENABLE_TDX:
        logger.error("ENABLE_TDX=true but %s. Refusing to start in degraded mode.", message)
        raise RuntimeError(f"ENABLE_TDX=true requires RTMR extend support; {message}")
    logger.warning(
        "NON-TEE MODE: %s — running without hardware measurement extensions (development/testing only)",
        message,
    )
    return None

# ---------------------------------------------------------------------------
# Submit daemon thread
# ---------------------------------------------------------------------------

_stop_daemon = threading.Event()
MAX_RETRIES = 10
POLL_INTERVAL = 5.0
QUEUE_SNAPSHOT_HEARTBEAT_TICKS = max(1, int(os.environ.get("TRUCON_QUEUE_SNAPSHOT_HEARTBEAT_TICKS", "12")))
_bundle_mirror: Optional[OciBundleMirror] = None
_last_queue_snapshot: Optional[tuple[int, int, int, int, int]] = None
_last_queue_snapshot_tick = 0
_queue_snapshot_tick = 0


def _extract_bundle_payload_b64(bundle_json: str) -> str:
    bundle = Bundle.from_json(bundle_json)
    envelope = bundle._dsse_envelope
    if envelope is None:
        raise ValueError("Bundle does not contain a DSSE envelope")
    envelope_json = json.loads(envelope.to_json())
    payload_b64 = envelope_json.get("payload")
    if not isinstance(payload_b64, str) or not payload_b64:
        raise ValueError("Bundle DSSE envelope is missing payload")
    return payload_b64


def _enqueue_mirror_publish_for_record(record: Any, log_id: Optional[str]) -> None:
    payload = json.loads(record["payload"])
    bundle_json = payload.get("bundle")
    if not isinstance(bundle_json, str) or not bundle_json:
        return

    payload_hash = _compute_bundle_payload_hash(bundle_json)
    payload_b64 = _extract_bundle_payload_b64(bundle_json)
    annotations = build_mirror_annotations(
        chain_id=record["chain_id"],
        sequence_num=record["sequence_num"],
        event_digest=record["event_digest"] if "event_digest" in record.keys() else None,
        rekor_log_id=log_id,
        payload_b64=payload_b64,
        event_id=record["event_id"] if "event_id" in record.keys() else None,
        prev_event_digest=record["prev_event_digest"] if "prev_event_digest" in record.keys() else None,
        prev_lookup_hash=record["prev_lookup_hash"] if "prev_lookup_hash" in record.keys() else None,
    )
    enqueue_mirror_publish(
        record_id=record["record_id"],
        chain_id=record["chain_id"],
        payload_hash=payload_hash,
        bundle_json=bundle_json,
        annotations=annotations,
    )


def _drain_mirror_publish_queue() -> None:
    if _bundle_mirror is None:
        return

    for job in get_pending_mirror_publishes():
        try:
            manifest = _bundle_mirror.publish_bundle(
                payload_hash=job["payload_hash"],
                bundle_json=job["bundle_json"],
                annotations=json.loads(job["annotations"]),
            )
            update_mirror_publish_status(
                job["record_id"],
                "PUBLISHED",
                artifact_digest=manifest.get("artifactDigest"),
                last_error=None,
            )
        except Exception as exc:
            logger.warning("Mirror publish failed for record %s: %s", job["record_id"], exc)
            update_mirror_publish_status(
                job["record_id"],
                "FAILED_RETRYABLE",
                last_error=str(exc),
                increment_retry_count=True,
            )


def _queue_snapshot_tuple(stats: Dict[str, int]) -> tuple[int, int, int, int, int]:
    return (
        stats['queued_count'],
        stats['submitting_count'],
        stats['failed_retryable_count'],
        stats['failed_terminal_count'],
        stats['total_retry_count'],
    )


def _emit_queue_snapshot(stats: Dict[str, int]) -> None:
    global _last_queue_snapshot, _last_queue_snapshot_tick, _queue_snapshot_tick

    snapshot = _queue_snapshot_tuple(stats)
    _queue_snapshot_tick += 1
    should_emit = _last_queue_snapshot != snapshot

    if not should_emit and (_queue_snapshot_tick - _last_queue_snapshot_tick) >= QUEUE_SNAPSHOT_HEARTBEAT_TICKS:
        should_emit = True

    if not should_emit:
        return

    _last_queue_snapshot = snapshot
    _last_queue_snapshot_tick = _queue_snapshot_tick
    logger.info(
        "metric=queue_snapshot queue_depth=%d submitting=%d failed_retryable=%d failed_terminal=%d total_retries=%d",
        snapshot[0],
        snapshot[1],
        snapshot[2],
        snapshot[3],
        snapshot[4],
    )

def _submit_daemon_loop():
    """Background thread: drain commit_queue to Rekor in sequence order."""
    logger.info("Submit daemon started")
    while not _stop_daemon.is_set():
        try:
            _submit_daemon_tick()
        except Exception as e:
            logger.error("Submit daemon error: %s", e)
        _stop_daemon.wait(timeout=POLL_INTERVAL)
    logger.info("Submit daemon stopped")

def _submit_daemon_tick():
    """One polling cycle of the submit daemon."""
    chain_ids = get_all_chain_ids()
    for chain_id in chain_ids:
        # Check for FAILED records blocking this chain
        failed = get_failed_by_chain(chain_id)
        if failed:
            # FAILED_RETRYABLE records: reset to PENDING for retry
            for f in failed:
                if f['status'] == 'FAILED_RETRYABLE':
                    update_status(f['record_id'], 'PENDING')
                    logger.info("Record %s reset from FAILED_RETRYABLE to PENDING for retry", f['record_id'])
            # Re-check: only FAILED_TERMINAL blocks the chain
            failed_terminal = [f for f in failed if f['status'] == 'FAILED_TERMINAL']
            if failed_terminal:
                min_failed_seq = failed_terminal[0]['sequence_num']
            else:
                min_failed_seq = None
        else:
            min_failed_seq = None

        pending = get_pending_by_chain(chain_id)
        for record in pending:
            seq = record['sequence_num']
            # Don't submit past a FAILED_TERMINAL record
            if min_failed_seq is not None and seq > min_failed_seq:
                break

            record_id = record['record_id']
            payload = json.loads(record['payload'])
            bundle_json = payload.get('bundle')

            if not bundle_json:
                logger.warning("Record %s has no bundle in payload, skipping", record_id)
                continue

            # Mark SUBMITTING before backend call
            set_status_submitting(record_id)
            t_submit = time.perf_counter()

            try:
                from sigstore.models import Bundle
                bundle = Bundle.from_json(bundle_json)

                if _immutable_log:
                    log_id, status, _receipt = _immutable_log.submit_bundle(bundle)
                    if status == "confirmed":
                        confirmed_rekor = _extract_confirmed_rekor_identifiers(log_id, _receipt)
                        update_record_confirmed(record_id, log_id)
                        submit_ms = (time.perf_counter() - t_submit) * 1000
                        logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "confirmed")
                        # Emit confirmation_lag if created_at is available
                        created_at = record['created_at'] if 'created_at' in record.keys() else None
                        if created_at:
                            confirmed_at = datetime.utcnow()
                            created_dt = datetime.fromisoformat(created_at)
                            lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
                            logger.info("metric=confirmation_lag lag_ms=%.1f record_id=%s", lag_ms, record_id)
                        # Update chain_state head_log_id
                        update_chain_state(
                            chain_id=chain_id,
                            head_record_id=record_id,
                            sequence_num=seq,
                            head_log_id=log_id,
                        )
                        _enqueue_mirror_publish_for_record(record, log_id)
                        logger.info(
                            "Record %s confirmed with confirmed_rekor_log_id=%s confirmed_rekor_uuid=%s confirmed_rekor_log_index=%s sequence_num=%s chain_id=%s",
                            record_id,
                            confirmed_rekor["confirmed_rekor_log_id"],
                            confirmed_rekor["confirmed_rekor_uuid"],
                            confirmed_rekor["confirmed_rekor_log_index"],
                            seq,
                            chain_id,
                        )
                    else:
                        submit_ms = (time.perf_counter() - t_submit) * 1000
                        logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                        _handle_retry(record_id)
                else:
                    # No immutable log backend — mark confirmed (testing/dev)
                    mock_log_id = f"mock-{uuid.uuid4().hex[:8]}"
                    update_record_confirmed(record_id, mock_log_id)
                    submit_ms = (time.perf_counter() - t_submit) * 1000
                    logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "confirmed")
                    # Emit confirmation_lag if created_at is available
                    created_at = record['created_at'] if 'created_at' in record.keys() else None
                    if created_at:
                        confirmed_at = datetime.utcnow()
                        created_dt = datetime.fromisoformat(created_at)
                        lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
                        logger.info("metric=confirmation_lag lag_ms=%.1f record_id=%s", lag_ms, record_id)
                    _enqueue_mirror_publish_for_record(record, mock_log_id)
                    logger.info("Record %s mock-confirmed (no immutable log)", record_id)

            except Exception as e:
                submit_ms = (time.perf_counter() - t_submit) * 1000
                logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                logger.error("Failed to submit record %s to Rekor: %s", record_id, e)
                _handle_retry(record_id)

    _drain_mirror_publish_queue()

    # Emit queue snapshot at end of each tick
    stats = get_queue_stats()
    _emit_queue_snapshot(stats)

def _handle_retry(record_id: str):
    """Increment retry; transition to FAILED_RETRYABLE or FAILED_TERMINAL."""
    increment_retry(record_id, 'FAILED_RETRYABLE')
    # Re-read to check current retry_count
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT retry_count FROM commit_queue WHERE record_id = ?', (record_id,)
        ).fetchone()
        if row and row['retry_count'] >= MAX_RETRIES:
            update_status(record_id, 'FAILED_TERMINAL')
            logger.warning("Record %s moved to FAILED_TERMINAL after %d retries", record_id, MAX_RETRIES)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _local_mr, _immutable_log, _quote_adapter, _uds_gateway, _bundle_mirror, _AUTH_DISABLED

    # Service authentication startup checks
    if _AUTH_DISABLED:
        logger.warning("⚠ TruCon service authentication DISABLED — development mode only")
    elif not _SERVICE_TOKEN and not _TRUCON_UDS_PATH:
        if _ENABLE_TDX:
            logger.error("Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH is configured while auth is enabled. Refusing to start.")
            raise RuntimeError("Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH is configured while auth is enabled")
        logger.warning(
            "Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH is configured while auth is enabled. Falling back to auth-disabled development mode."
        )
        _AUTH_DISABLED = True

    # Single-instance enforcement
    acquire_instance_lock()

    # Initialize database
    init_db()

    # Crash recovery
    _crash_recovery()

    # Initialize adapters
    try:
        _local_mr = _initialize_local_mr_adapter()
    except Exception as e:
        if _ENABLE_TDX:
            raise
        logger.warning("Could not init local MR adapter: %s", e)

    mirror_location = (
        os.environ.get("TRUCON_BUNDLE_MIRROR")
        or os.environ.get("TRUCON_BUNDLE_MIRROR_URL")
        or os.environ.get("TRUCON_BUNDLE_MIRROR_DIR")
    )
    _bundle_mirror = OciBundleMirror(mirror_location) if mirror_location else None
    _immutable_log = SigstoreLogAdapter(bundle_mirror=_bundle_mirror)
    _quote_adapter = TdxQuoteAdapter()

    if _TRUCON_UDS_PATH:
        _uds_gateway = TruConUnixSocketGateway(
            socket_path=_TRUCON_UDS_PATH,
            internal_proxy_secret=_INTERNAL_PROXY_SECRET,
            forward_port=_TRUCON_HTTP_PORT,
            auth_disabled=_AUTH_DISABLED,
        )
        _uds_gateway.start()

    # Start submit daemon thread
    daemon_thread = threading.Thread(target=_submit_daemon_loop, daemon=True, name="submit-daemon")
    daemon_thread.start()

    yield

    # Shutdown
    _stop_daemon.set()
    daemon_thread.join(timeout=10)
    if _uds_gateway is not None:
        _uds_gateway.stop()
        _uds_gateway = None
    _bundle_mirror = None
    release_instance_lock()
    logger.info("TruCon shut down")


app = FastAPI(
    title="TruCon — Trusted Log Sequencer",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Service authentication middleware
# ---------------------------------------------------------------------------

_AUTH_DISABLED = os.environ.get("TRUCON_AUTH_DISABLED", "").lower() == "true"
_SERVICE_TOKEN = os.environ.get("TRUCON_SERVICE_TOKEN", "")
_TRUCON_UDS_PATH = os.environ.get("TRUCON_UDS_PATH", "")
_ENABLE_TDX = os.environ.get("ENABLE_TDX", "true").lower() == "true"
_TRUCON_HTTP_PORT = int(os.environ.get("TRUCON_PORT", "8001"))
_INTERNAL_PROXY_SECRET = secrets.token_urlsafe(32)
_uds_gateway: Optional[TruConUnixSocketGateway] = None


def _authorize_caller(caller_service: str, request: Request) -> Optional[JSONResponse]:
    if caller_service in {"auth_bypass", "compat_http", "tc_api"}:
        return None

    if caller_service == "docktap":
        if request.method == "POST" and request.url.path == "/commit":
            return None
        return JSONResponse(
            status_code=403,
            content={"detail": f"Caller '{caller_service}' is not authorized for {request.method} {request.url.path}"},
        )

    return JSONResponse(status_code=401, content={"detail": "Unrecognized caller identity"})

@app.middleware("http")
async def service_auth_middleware(request: Request, call_next):
    if _AUTH_DISABLED:
        request.state.caller_service = "auth_bypass"
        request.state.auth_transport = "disabled"
        return await call_next(request)

    proxy_secret = request.headers.get(INTERNAL_PROXY_SECRET_HEADER)
    if proxy_secret and hmac.compare_digest(proxy_secret, _INTERNAL_PROXY_SECRET):
        caller_service = request.headers.get(CALLER_SERVICE_HEADER)
        if caller_service not in {"tc_api", "docktap"}:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing caller service"})

        request.state.caller_service = caller_service
        request.state.auth_transport = request.headers.get(AUTH_TRANSPORT_HEADER, "uds")
        request.state.peer_pid = request.headers.get(PEER_PID_HEADER)
        request.state.peer_uid = request.headers.get(PEER_UID_HEADER)
        request.state.peer_gid = request.headers.get(PEER_GID_HEADER)

        denial = _authorize_caller(caller_service, request)
        if denial is not None:
            return denial
        return await call_next(request)

    auth_header = request.headers.get("authorization")
    if not auth_header:
        return JSONResponse(status_code=401, content={"detail": "Missing Authorization header"})

    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Invalid Authorization scheme, expected Bearer"})

    token = auth_header[7:]  # len("Bearer ") == 7
    if not hmac.compare_digest(token, _SERVICE_TOKEN):
        return JSONResponse(status_code=401, content={"detail": "Invalid service token"})

    request.state.caller_service = request.headers.get(CALLER_SERVICE_HEADER, "compat_http")
    request.state.auth_transport = "http_compat"
    denial = _authorize_caller(request.state.caller_service, request)
    if denial is not None:
        return denial

    return await call_next(request)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/init-chain/{chain_id}/baseline", response_model=InitChainBaselineResponse)
def get_init_chain_baseline(chain_id: str):
    """
    Phase 1 of chain initialization: read platform baseline (RTMR[2], CCEL digest)
    and return an init_token for TOCTOU protection.
    """
    with _sequencer_lock:
        state = get_chain_state(chain_id)
        if state:
            raise HTTPException(status_code=409, detail=f"Chain '{chain_id}' already initialized")

        # Read RTMR[2] snapshot
        rtmr_value = None
        if _local_mr:
            try:
                rtmr_value = _local_mr.read(RTMR_INDEX)
            except Exception as e:
                logger.error("Failed to read RTMR[%d]: %s", RTMR_INDEX, e)

        # Compute CCEL baseline material
        ccel_digest = compute_ccel_digest()
        ccel_eventlog_b64 = read_ccel_eventlog_b64()

        # Generate init_token
        init_token = secrets.token_urlsafe(32)
        _pending_init_tokens[init_token] = {
            "chain_id": chain_id,
            "rtmr_value": rtmr_value,
            "ccel_digest": ccel_digest,
            "ccel_eventlog_b64": ccel_eventlog_b64,
        }

        return InitChainBaselineResponse(
            rtmr_value=rtmr_value,
            ccel_digest=ccel_digest,
            ccel_eventlog_b64=ccel_eventlog_b64,
            init_token=init_token,
        )


@app.post("/commit-intents/reserve", response_model=CommitIntentReserveResponse)
def reserve_commit_intent(req: CommitIntentReserveRequest):
    """Allocate a durable predecessor contract that the caller must sign."""
    with _sequencer_lock:
        expire_active_commit_intents()

        if req.idempotency_key:
            existing_record = get_record_by_idempotency_key(req.idempotency_key, req.chain_id)
            if existing_record is not None:
                return CommitIntentReserveResponse(
                    intent_token=None,
                    chain_id=req.chain_id,
                    sequence_num=existing_record["sequence_num"],
                    prev_event_digest=existing_record["prev_event_digest"] if "prev_event_digest" in existing_record.keys() else None,
                    prev_lookup_hash=existing_record["prev_lookup_hash"] if "prev_lookup_hash" in existing_record.keys() else None,
                    expires_at=None,
                    committed=True,
                    record_id=existing_record["record_id"],
                )

            existing_intent = get_commit_intent_by_idempotency_key(req.chain_id, req.idempotency_key)
            if existing_intent is not None and existing_intent["status"] == "ACTIVE" and not _intent_expired(existing_intent):
                return CommitIntentReserveResponse(**_intent_response_from_row(existing_intent))

        active_intent = get_active_commit_intent_for_chain(req.chain_id)
        if active_intent is not None:
            if _intent_expired(active_intent):
                update_commit_intent_status(active_intent["intent_token"], "EXPIRED")
            elif not req.idempotency_key or active_intent["idempotency_key"] != req.idempotency_key:
                raise HTTPException(status_code=409, detail=f"Chain '{req.chain_id}' already has an active commit intent")

        state = get_chain_state(req.chain_id)
        if req.is_baseline:
            if state is not None:
                raise HTTPException(status_code=409, detail=f"Chain '{req.chain_id}' already initialized")
            sequence_num = 1
            prev_event_digest = None
            prev_lookup_hash = None
        else:
            if state is None:
                raise HTTPException(status_code=409, detail=f"Chain '{req.chain_id}' is not initialized")
            head_record = get_record_by_id(state["head_record_id"])
            if head_record is None:
                raise HTTPException(status_code=500, detail=f"Chain '{req.chain_id}' head record is missing")
            sequence_num = state["sequence_num"] + 1
            prev_event_digest = head_record["event_digest"] if "event_digest" in head_record.keys() else None
            prev_lookup_hash = _compute_record_lookup_hash(head_record)

        intent_token = secrets.token_urlsafe(32)
        expires_at = datetime.utcfromtimestamp(time.time() + INTENT_TTL_SECONDS).isoformat()
        create_commit_intent(
            intent_token=intent_token,
            chain_id=req.chain_id,
            idempotency_key=req.idempotency_key,
            sequence_num=sequence_num,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            expires_at=expires_at,
        )

        return CommitIntentReserveResponse(
            intent_token=intent_token,
            chain_id=req.chain_id,
            sequence_num=sequence_num,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            expires_at=expires_at,
            committed=False,
            record_id=None,
        )


@app.post("/init-chain", response_model=InitChainResponse)
def init_chain(req: InitChainRequest, request: Request):
    """
    Phase 2 of chain initialization: validate init_token and insert Event Log 0
    (baseline record) into the commit queue.
    """
    with _sequencer_lock:
        expire_active_commit_intents()

        # Validate init_token
        token_data = _pending_init_tokens.pop(req.init_token, None)
        if token_data is None:
            raise HTTPException(status_code=400, detail="Invalid or expired init_token")

        if token_data["chain_id"] != req.chain_id:
            raise HTTPException(status_code=400, detail="init_token chain_id mismatch")

        # Ensure chain is still uninitialized (TOCTOU guard)
        state = get_chain_state(req.chain_id)
        if state:
            raise HTTPException(status_code=409, detail=f"Chain '{req.chain_id}' already initialized")

        intent = get_commit_intent_by_token(req.intent_token)
        if intent is None:
            raise HTTPException(status_code=400, detail="Invalid or expired intent_token")
        if intent["chain_id"] != req.chain_id:
            raise HTTPException(status_code=400, detail="intent_token chain_id mismatch")
        if intent["status"] != "ACTIVE" or _intent_expired(intent):
            if intent["status"] == "ACTIVE" and _intent_expired(intent):
                update_commit_intent_status(req.intent_token, "EXPIRED")
            raise HTTPException(status_code=400, detail="Intent token is not active")
        if intent["sequence_num"] != 1:
            raise HTTPException(status_code=400, detail="Baseline intent must reserve sequence_num=1")

        try:
            predicate = _extract_bundle_predicate(req.signed_bundle)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid baseline bundle: {exc}") from exc

        if predicate.get("chain_id") != req.chain_id:
            raise HTTPException(status_code=400, detail="Baseline bundle chain_id mismatch")
        if predicate.get("sequence_num") != 1:
            raise HTTPException(status_code=400, detail="Baseline bundle sequence_num mismatch")
        if predicate.get("prev_event_digest") is not None or predicate.get("prev_lookup_hash") is not None:
            raise HTTPException(status_code=400, detail="Baseline bundle must use null predecessor fields")

        event_digest = predicate.get("digest")
        if not isinstance(event_digest, str):
            raise HTTPException(status_code=400, detail="Baseline bundle is missing digest")

        record_id = str(uuid.uuid4())
        sequence_num = 1

        caller_service = getattr(request.state, "caller_service", None)
        auth_transport = getattr(request.state, "auth_transport", None)
        owner_attestation = _build_chain_owner_attestation(
            chain_id=req.chain_id,
            sequence_num=sequence_num,
            baseline_rtmr=token_data["rtmr_value"],
            ccel_digest=token_data["ccel_digest"],
            owner_pub_key=req.pub_key,
        )

        # INSERT baseline record (Event Log 0)
        # rtmr_extended=True: RTMR value was captured (read, not extended).
        # This flag must be True for the submit daemon and crash recovery to
        # handle the record correctly through existing infrastructure.
        insert_record(
            record_id=record_id,
            event_id=f"evt-log0-{req.chain_id}",
            payload={
                "bundle": req.signed_bundle,
                "chain_id": req.chain_id,
                "pub_key": req.pub_key,
                "owner_attestation": owner_attestation,
                "is_baseline": True,
                "caller_service": caller_service,
                "auth_transport": auth_transport,
            },
            status="PENDING",
            chain_id=req.chain_id,
            rtmr_extended=True,
            prev_log_id=None,
            prev_event_digest=None,
            prev_lookup_hash=None,
            intent_token=req.intent_token,
            mr_value=token_data["rtmr_value"],
            sequence_num=sequence_num,
            event_digest=event_digest,
            idempotency_key=intent["idempotency_key"],
            instance_id=None,
        )

        # Initialize chain_state
        update_chain_state(
            chain_id=req.chain_id,
            head_record_id=record_id,
            sequence_num=sequence_num,
            mr_value=token_data["rtmr_value"],
        )
        update_commit_intent_status(req.intent_token, "CONSUMED", record_id=record_id)

        logger.info(
            "Chain '%s' initialized with baseline record %s caller_service=%s auth_transport=%s",
            req.chain_id,
            record_id,
            caller_service,
            auth_transport,
        )
        return InitChainResponse(record_id=record_id, sequence_num=sequence_num)


@app.post("/commit", response_model=CommitResponse)
def commit(req: CommitRequest, request: Request):
    """
    Sequence a signed bundle: RTMR extend + SQLite INSERT + chain_state update.
    All three operations are serialized behind a threading.Lock().
    """
    t0 = time.perf_counter()
    record_id = str(uuid.uuid4())
    event_id = req.event_id or f"evt-{uuid.uuid4().hex[:8]}"
    caller_service = getattr(request.state, "caller_service", None)
    auth_transport = getattr(request.state, "auth_transport", None)

    with _sequencer_lock:
        expire_active_commit_intents()

        # 0. Idempotency check — before any side effects
        if req.idempotency_key:
            existing = get_record_by_idempotency_key(req.idempotency_key, req.chain_id)
            if existing:
                latency_ms = (time.perf_counter() - t0) * 1000
                logger.info(
                    "metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s",
                    latency_ms, existing['record_id'], True,
                )
                logger.info(
                    "metric=idempotency_hit key=%s chain_id=%s record_id=%s",
                    req.idempotency_key, req.chain_id, existing['record_id'],
                )
                return CommitResponse(
                    record_id=existing['record_id'],
                    sequence_num=existing['sequence_num'],
                    mr_value=existing['mr_value'],
                    prev_mr_value=None,
                )

        if req.intent_token:
            intent = get_commit_intent_by_token(req.intent_token)
            if intent is None:
                raise HTTPException(status_code=400, detail="Invalid or expired intent_token")
            if intent["chain_id"] != req.chain_id:
                raise HTTPException(status_code=400, detail="intent_token chain_id mismatch")
            if intent["status"] == "CONSUMED" and intent["record_id"]:
                existing = get_record_by_id(intent["record_id"])
                if existing is not None:
                    return CommitResponse(
                        record_id=existing["record_id"],
                        sequence_num=existing["sequence_num"],
                        mr_value=existing["mr_value"],
                        prev_mr_value=None,
                    )
            if intent["status"] != "ACTIVE" or _intent_expired(intent):
                if intent["status"] == "ACTIVE" and _intent_expired(intent):
                    update_commit_intent_status(req.intent_token, "EXPIRED")
                raise HTTPException(status_code=400, detail="Intent token is not active")

            try:
                predicate = _extract_bundle_predicate(req.bundle)
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Invalid DSSE bundle: {exc}") from exc

            if predicate.get("chain_id") != req.chain_id:
                raise HTTPException(status_code=400, detail="Bundle chain_id mismatch")
            if predicate.get("sequence_num") != intent["sequence_num"]:
                raise HTTPException(status_code=400, detail="Bundle sequence_num mismatch")
            if predicate.get("prev_event_digest") != intent["prev_event_digest"]:
                raise HTTPException(status_code=400, detail="Bundle prev_event_digest mismatch")
            if predicate.get("prev_lookup_hash") != intent["prev_lookup_hash"]:
                raise HTTPException(status_code=400, detail="Bundle prev_lookup_hash mismatch")
            if predicate.get("digest") != req.event_digest:
                raise HTTPException(status_code=400, detail="Bundle digest mismatch")

            state = get_chain_state(req.chain_id)
            if state:
                prev_log_id = state["head_log_id"]
                if state["sequence_num"] + 1 != intent["sequence_num"]:
                    raise HTTPException(status_code=409, detail="Reserved sequence no longer matches chain head")
            else:
                prev_log_id = None
                if intent["sequence_num"] != 1:
                    raise HTTPException(status_code=409, detail="Reserved sequence requires initialized chain state")

            event_id = req.event_id or predicate.get("event_id") or event_id
            sequence_num = intent["sequence_num"]
            owner_pub_key = _get_chain_owner_pub_key(req.chain_id)
            if owner_pub_key is not None:
                if req.owner_authorization is None:
                    raise HTTPException(status_code=400, detail="Missing owner authorization")
                try:
                    owner_ok = verify_owner_authorization(
                        req.owner_authorization,
                        owner_pub_key_pem=owner_pub_key,
                        chain_id=req.chain_id,
                        sequence_num=sequence_num,
                        prev_event_digest=intent["prev_event_digest"],
                        prev_lookup_hash=intent["prev_lookup_hash"],
                        event_digest=req.event_digest,
                    )
                except Exception as exc:
                    raise HTTPException(status_code=400, detail=f"Invalid owner authorization: {exc}") from exc
                if not owner_ok:
                    raise HTTPException(status_code=400, detail="Owner authorization signature mismatch")

            mr_value, prev_mr_value = None, None
            if _local_mr:
                try:
                    mr_value, prev_mr_value = _local_mr.extend(RTMR_INDEX, req.event_digest)
                except Exception as e:
                    logger.error("RTMR extend failed: %s", e)
                    raise HTTPException(status_code=500, detail=f"RTMR extend failed: {e}")

            insert_record(
                record_id=record_id,
                event_id=event_id,
                payload={
                    "bundle": req.bundle,
                    "chain_id": req.chain_id,
                    "owner_authorization": req.owner_authorization,
                    "caller_service": caller_service,
                    "auth_transport": auth_transport,
                },
                status="PENDING",
                chain_id=req.chain_id,
                rtmr_extended=True,
                prev_log_id=prev_log_id,
                prev_event_digest=intent["prev_event_digest"],
                prev_lookup_hash=intent["prev_lookup_hash"],
                intent_token=req.intent_token,
                mr_value=mr_value,
                sequence_num=sequence_num,
                event_digest=req.event_digest,
                idempotency_key=req.idempotency_key or intent["idempotency_key"],
                instance_id=req.instance_id,
            )

            update_chain_state(
                chain_id=req.chain_id,
                head_record_id=record_id,
                sequence_num=sequence_num,
                mr_value=mr_value,
            )
            update_commit_intent_status(req.intent_token, "CONSUMED", record_id=record_id)

            logger.info(
                "Accepted reservation-backed commit record_id=%s chain_id=%s sequence_num=%s caller_service=%s auth_transport=%s",
                record_id,
                req.chain_id,
                sequence_num,
                caller_service,
                auth_transport,
            )

            latency_ms = (time.perf_counter() - t0) * 1000
            logger.info(
                "metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s",
                latency_ms, record_id, False,
            )

            return CommitResponse(
                record_id=record_id,
                sequence_num=sequence_num,
                mr_value=mr_value,
                prev_mr_value=prev_mr_value,
            )

        # Legacy commit requires an initialized chain head. The default chain is not exempt:
        # Event Log 0 must exist before any externally replayable history can be built.
        if get_chain_state(req.chain_id) is None:
            raise HTTPException(
                status_code=409,
                detail=f"Chain '{req.chain_id}' is not initialized; create Event Log 0 before committing",
            )

        # 1. Read current chain state
        state = get_chain_state(req.chain_id)
        if state:
            prev_log_id = state['head_log_id']
            sequence_num = state['sequence_num'] + 1
        else:
            prev_log_id = None
            sequence_num = 1

        # 2. RTMR extend
        mr_value, prev_mr_value = None, None
        if _local_mr:
            try:
                mr_value, prev_mr_value = _local_mr.extend(RTMR_INDEX, req.event_digest)
            except Exception as e:
                logger.error("RTMR extend failed: %s", e)
                raise HTTPException(status_code=500, detail=f"RTMR extend failed: {e}")

        # 3. INSERT into commit_queue with rtmr_extended=TRUE
        insert_record(
            record_id=record_id,
            event_id=event_id,
            payload={
                "bundle": req.bundle,
                "chain_id": req.chain_id,
                "caller_service": caller_service,
                "auth_transport": auth_transport,
            },
            status="PENDING",
            chain_id=req.chain_id,
            rtmr_extended=True,
            prev_log_id=prev_log_id,
            mr_value=mr_value,
            sequence_num=sequence_num,
            event_digest=req.event_digest,
            idempotency_key=req.idempotency_key,
            instance_id=req.instance_id,
        )

        # 4. UPDATE chain_state
        update_chain_state(
            chain_id=req.chain_id,
            head_record_id=record_id,
            sequence_num=sequence_num,
            mr_value=mr_value,
        )

        logger.info(
            "Accepted commit record_id=%s chain_id=%s sequence_num=%s caller_service=%s auth_transport=%s",
            record_id,
            req.chain_id,
            sequence_num,
            caller_service,
            auth_transport,
        )

    latency_ms = (time.perf_counter() - t0) * 1000
    logger.info(
        "metric=commit_latency latency_ms=%.1f record_id=%s idempotent=%s",
        latency_ms, record_id, False,
    )

    return CommitResponse(
        record_id=record_id,
        sequence_num=sequence_num,
        mr_value=mr_value,
        prev_mr_value=prev_mr_value,
    )


@app.get("/chain-state/{chain_id}", response_model=ChainStateResponse)
def get_chain_state_endpoint(chain_id: str):
    """Return current chain state for a given chain_id."""
    state = get_chain_state(chain_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No chain state for '{chain_id}'")
    return ChainStateResponse(
        chain_id=chain_id,
        head_record_id=state['head_record_id'],
        head_log_id=state['head_log_id'],
        sequence_num=state['sequence_num'],
        mr_value=state['mr_value'],
        updated_at=state['updated_at'],
    )


@app.get(
    "/evidence/{chain_id}",
    response_model=AttestedHeadEvidence,
    responses={404: {"model": EvidenceErrorResponse}, 409: {"model": EvidenceErrorResponse}, 500: {"model": EvidenceErrorResponse}},
)
def get_attested_head_evidence(chain_id: str):
    """Return attested-head evidence for the latest confirmed public head of a chain."""
    state = get_chain_state(chain_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No chain state for '{chain_id}'")

    confirmed = get_latest_confirmed_record(chain_id)
    if not confirmed or not confirmed["log_id"]:
        raise HTTPException(status_code=409, detail=f"Chain '{chain_id}' has no confirmed immutable-log head")
    if not confirmed["mr_value"]:
        raise HTTPException(status_code=409, detail=f"Chain '{chain_id}' has no measured confirmed head state")
    if _quote_adapter is None:
        raise HTTPException(status_code=500, detail="Quote adapter is unavailable")

    expected_value = compute_binding_expected_value(
        chain_id=chain_id,
        sequence_num=confirmed["sequence_num"],
        head_log_id=confirmed["log_id"],
        mr_value=confirmed["mr_value"],
    )

    try:
        quote_material = _quote_adapter.quote(expected_value)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Quote acquisition failed: {exc}") from exc

    if quote_material.report_data != expected_value:
        raise HTTPException(status_code=500, detail="Quote-backed report data did not match the expected binding value")

    evidence = validate_attested_head_evidence_payload(
        {
            "version": "v1",
            "tee_type": "tdx",
            "chain_id": chain_id,
            "sequence_num": confirmed["sequence_num"],
            "head_log_id": confirmed["log_id"],
            "mr_value": confirmed["mr_value"],
            "generated_at": datetime.utcnow(),
            "quote": quote_material.quote,
            "quote_format": quote_material.quote_format,
            "head_event_digest": confirmed["event_digest"],
            "report_data_binding": {
                "algorithm": BINDING_ALGORITHM,
                "bound_fields": list(REQUIRED_BOUND_FIELDS),
                "expected_value": expected_value,
            },
        }
    )
    return evidence


@app.get("/status", response_model=CommitQueueStatusResponse)
def get_status():
    """Return queue statistics matching CommitQueueStatus contract."""
    stats = get_queue_stats()
    return CommitQueueStatusResponse(
        has_queued_records=stats['queued_count'] > 0,
        queued_record_count=stats['queued_count'],
        next_record_id=stats.get('next_record_id'),
        submitting_count=stats['submitting_count'],
        failed_retryable_count=stats['failed_retryable_count'],
        failed_terminal_count=stats['failed_terminal_count'],
        total_retry_count=stats['total_retry_count'],
    )


@app.get("/state", response_model=LatestStateResponse)
def get_state():
    """Return LatestState for the default chain."""
    state = get_latest_state('default')
    return LatestStateResponse(**state)


def _record_has_signed_predecessor_contract(record: Any) -> bool:
    sequence_num = record['sequence_num']
    return sequence_num > 1 and (
        ('prev_event_digest' in record.keys() and record['prev_event_digest'] is not None)
        or ('prev_lookup_hash' in record.keys() and record['prev_lookup_hash'] is not None)
    )


def _classify_verify_chain_boundary(record: Any, records: list[Any]) -> Optional[str]:
    sequence_num = record['sequence_num']
    if sequence_num <= 1 or _record_has_signed_predecessor_contract(record):
        return None

    lower_signed = any(
        other['sequence_num'] < sequence_num and _record_has_signed_predecessor_contract(other)
        for other in records
    )
    if lower_signed:
        return "invalid"

    higher_signed = any(
        other['sequence_num'] > sequence_num and _record_has_signed_predecessor_contract(other)
        for other in records
    )
    if higher_signed:
        return "degraded"

    return None


@app.get("/verify-chain/{chain_id}", response_model=ChainVerificationResponse)
def verify_chain(chain_id: str):
    """
    Full chain traversal verification.

    Checks sequence continuity, RTMR chain integrity (if event_digest is
    available), and Rekor confirmation status for every record in the chain.
    """
    records = get_chain_records(chain_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No records for chain '{chain_id}'")

    entries: list[ChainEntryResult] = []
    valid = True
    first_error_at: Optional[int] = None
    mr_verified = 0
    rekor_confirmed = 0
    rekor_pending = 0
    expected_seq = 1
    prev_mr: Optional[str] = None
    prev_confirmed_record: Optional[Any] = None
    baseline_error: Optional[str] = None
    # Determine if RTMR is available: at least one non-NULL mr_value
    rtmr_available = any(r['mr_value'] is not None for r in records)
    owner_pub_key = _get_chain_owner_pub_key_from_records(records)

    if chain_id != 'default' and not _record_is_baseline(records[0]):
        baseline_error = f"non-default chain '{chain_id}' does not begin with Event Log 0"
        valid = False
        first_error_at = records[0]['sequence_num']

    for r in records:
        seq = r['sequence_num']
        record_id = r['record_id']
        event_id = r['event_id']
        mr_value = r['mr_value']
        event_digest = r['event_digest'] if 'event_digest' in r.keys() else None
        rtmr_ext = bool(r['rtmr_extended'])
        is_confirmed = r['status'] == 'CONFIRMED' and r['log_id'] is not None
        error: Optional[str] = None
        mr_ok: Optional[bool] = None
        predecessor_ok: Optional[bool] = None
        predecessor_status: Optional[str] = None
        owner_ok: Optional[bool] = None
        owner_status: Optional[str] = None
        prev_event_digest = r['prev_event_digest'] if 'prev_event_digest' in r.keys() else None
        prev_lookup_hash = r['prev_lookup_hash'] if 'prev_lookup_hash' in r.keys() else None
        candidate_count: Optional[int] = None
        materialized_candidate_count: Optional[int] = None
        matched_candidate_count: Optional[int] = None
        boundary_status: Optional[str] = None
        payload = _record_payload_dict(r)

        if baseline_error and seq == records[0]['sequence_num']:
            error = baseline_error

        # 1. Sequence continuity check
        if seq != expected_seq:
            error = f"sequence gap: expected {expected_seq}, got {seq}"
            if valid:
                valid = False
                first_error_at = seq

        # 2. RTMR chain integrity check
        if _record_is_baseline(r):
            # Event Log 0 stores the observed baseline snapshot, not the result of
            # extending a prior MR value with its own digest.
            mr_ok = None
        elif mr_value is None or event_digest is None:
            # Cannot verify — skip
            mr_ok = None
        else:
            if prev_mr is not None:
                prev_bytes = bytes.fromhex(prev_mr)
            else:
                prev_bytes = b'\x00' * 48  # Initial RTMR is all zeros
            digest_bytes = bytes.fromhex(event_digest.removeprefix("sha384:"))
            expected_mr = hashlib.sha384(prev_bytes + digest_bytes).hexdigest()
            if mr_value == expected_mr:
                mr_ok = True
                mr_verified += 1
            else:
                mr_ok = False
                mr_error = f"RTMR mismatch: expected {expected_mr}, got {mr_value}"
                error = f"{error}; {mr_error}" if error else mr_error
                if valid:
                    valid = False
                    first_error_at = seq

        # 3. Rekor confirmation status
        rekor_ok = is_confirmed
        if is_confirmed:
            rekor_confirmed += 1
        else:
            rekor_pending += 1

        if is_confirmed and prev_event_digest is None and prev_lookup_hash is None:
            boundary_status = _classify_verify_chain_boundary(r, records)
            if boundary_status == "invalid":
                boundary_error = "signed predecessor contract regressed after reservation-backed replay began"
                error = f"{error}; {boundary_error}" if error else boundary_error
                if valid:
                    valid = False
                    first_error_at = seq

        # 4. Signed predecessor verification (non-TEE fallback)
        if not rtmr_available:
            if not is_confirmed:
                predecessor_ok = None
                predecessor_status = "unverifiable"
                candidate_count = None
                materialized_candidate_count = None
                matched_candidate_count = None
            elif seq == 1 and prev_event_digest is None and prev_lookup_hash is None:
                predecessor_ok = True
                predecessor_status = "origin"
                candidate_count = 0
                materialized_candidate_count = 0
                matched_candidate_count = 0
            elif prev_event_digest is None and prev_lookup_hash is None:
                predecessor_ok = False if boundary_status == "invalid" else None
                predecessor_status = "unverifiable"
                candidate_count = 0
                materialized_candidate_count = 0
                matched_candidate_count = 0
                link_error = "signed predecessor contract unavailable for confirmed replayable record"
                if boundary_status == "invalid":
                    link_error = "signed predecessor contract regressed after reservation-backed replay began"
                elif boundary_status == "degraded":
                    link_error = "signed predecessor contract unavailable at legacy-to-reservation replay boundary"
                error = f"{error}; {link_error}" if error else link_error
            else:
                candidate_count = 1 if prev_confirmed_record is not None else 0
                materialized_candidate_count = candidate_count
                expected_digest = prev_confirmed_record['event_digest'] if prev_confirmed_record is not None else None
                expected_lookup_hash = _compute_record_lookup_hash(prev_confirmed_record) if prev_confirmed_record is not None else None
                expected_sequence = prev_confirmed_record['sequence_num'] + 1 if prev_confirmed_record is not None else None
                predecessor_ok = (
                    prev_confirmed_record is not None
                    and seq == expected_sequence
                    and prev_event_digest == expected_digest
                    and prev_lookup_hash == expected_lookup_hash
                )
                matched_candidate_count = 1 if predecessor_ok else 0
                predecessor_status = "proven" if predecessor_ok else "missing"
                if candidate_count == 0:
                    predecessor_status = "missing"
                if not predecessor_ok:
                    link_error = (
                        f"signed predecessor mismatch: expected digest={expected_digest} lookup_hash={expected_lookup_hash}, "
                        f"got digest={prev_event_digest} lookup_hash={prev_lookup_hash}"
                    )
                    error = f"{error}; {link_error}" if error else link_error
                    if valid:
                        valid = False
                        first_error_at = seq

        if owner_pub_key is not None:
            if _record_is_baseline(r):
                owner_ok = True
                owner_status = "origin"
            elif not is_confirmed:
                owner_ok = None
                owner_status = "unverifiable"
            else:
                owner_authorization = payload.get("owner_authorization") if payload is not None else None
                if owner_authorization is None:
                    owner_ok = False
                    owner_status = "missing"
                    owner_error = "owner authorization missing for confirmed record"
                else:
                    try:
                        owner_ok = verify_owner_authorization(
                            owner_authorization,
                            owner_pub_key_pem=owner_pub_key,
                            chain_id=chain_id,
                            sequence_num=seq,
                            prev_event_digest=prev_event_digest,
                            prev_lookup_hash=prev_lookup_hash,
                            event_digest=event_digest,
                        )
                    except Exception as exc:
                        owner_ok = False
                        owner_status = "invalid"
                        owner_error = f"owner authorization invalid: {exc}"
                    else:
                        if owner_ok:
                            owner_status = "proven"
                        else:
                            owner_status = "invalid"
                            owner_error = "owner authorization signature mismatch"

                if owner_ok is False:
                    error = f"{error}; {owner_error}" if error else owner_error
                    if valid:
                        valid = False
                        first_error_at = seq

        entries.append(ChainEntryResult(
            seq=seq,
            record_id=record_id,
            event_id=event_id,
            mr_ok=mr_ok,
            rekor_ok=rekor_ok,
            rtmr_extended=rtmr_ext,
            mr_value=mr_value,
            predecessor_ok=predecessor_ok,
            predecessor_status=predecessor_status,
            owner_ok=owner_ok,
            owner_status=owner_status,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            candidate_count=candidate_count,
            materialized_candidate_count=materialized_candidate_count,
            matched_candidate_count=matched_candidate_count,
            boundary_status=boundary_status,
            error=error,
        ))

        # Advance state for next iteration
        if mr_value is not None:
            prev_mr = mr_value
        if is_confirmed:
            prev_confirmed_record = r
        expected_seq = seq + 1

    head_mr = records[-1]['mr_value'] if records else None

    return ChainVerificationResponse(
        valid=valid,
        chain_id=chain_id,
        total_entries=len(records),
        mr_verified=mr_verified,
        rekor_confirmed=rekor_confirmed,
        rekor_pending=rekor_pending,
        rtmr_available=rtmr_available,
        head_mr_value=head_mr,
        first_error_at=first_error_at,
        entries=entries,
    )


@app.get("/workloads/{workload_id}/instances", response_model=List[InstanceSummary])
def list_workload_instances(workload_id: str):
    """List all container instances for a workload."""
    rows = get_instances_for_workload(workload_id)
    return [InstanceSummary(**row) for row in rows]


@app.get("/instances/{instance_id}/events", response_model=List[EventSummary])
def list_instance_events(instance_id: str):
    """List all events for a specific container instance."""
    rows = get_events_for_instance(instance_id)
    return [EventSummary(**row) for row in rows]


@app.get("/workloads/{workload_id}/events", response_model=List[EventSummary])
def list_workload_events(workload_id: str):
    """List all events across all instances of a workload."""
    rows = get_events_for_workload(workload_id)
    return [EventSummary(**row) for row in rows]


def main() -> None:
    import uvicorn

    uvicorn.run("tc_api.trucon.app:app", host="0.0.0.0", port=8001, workers=1)


if __name__ == "__main__":
    main()

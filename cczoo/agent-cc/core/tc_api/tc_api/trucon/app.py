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
TruCon — Single-instance sequencer for the Trusted Container Log.

Serializes RTMR extend + SQLite INSERT behind a threading.Lock(),
maintains chain state, and embeds a submit daemon as a background thread.

MUST be run with --workers 1 to preserve lock semantics.
"""

import fcntl
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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from tlog.immutable import ImmutableLogAdapter

from .database import (
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
    get_failed_by_chain,
    get_highest_extended_record,
    get_latest_confirmed_record,
    get_pending_by_chain,
    get_pending_mirror_publishes,
    get_queue_stats,
    get_record_by_id,
    get_record_by_idempotency_key,
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
from tlog.backends.rekor.oci_mirror import OciBundleMirror, build_mirror_annotations
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from .adapters.ccel import compute_ccel_digest, read_ccel_eventlog_b64
from .adapters.tdx_quote import TdxQuoteAdapter
from .bundles import (
    compute_bundle_payload_hash,
    compute_record_lookup_hash,
    extract_bundle_payload_b64,
    extract_bundle_predicate,
    should_extend_rtmr,
)
from .chain_verification import (
    get_chain_owner_pub_key_from_records,
)
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
from .auth import authorize_caller
from .schemas import (
    CommitIntentReserveRequest,
    CommitIntentReserveResponse,
    CommitRequest,
    CommitResponse,
    EvidenceErrorResponse,
    InitChainBaselineResponse,
    InitChainRequest,
    InitChainResponse,
    OpenVikingEvidenceResponse,
    OpenVikingPostureResponse,
)
from .submit_daemon import SubmitDaemon
from . import submit_daemon as submit_daemon_mod
from .config import (
    AUTH_DISABLED as _AUTH_DISABLED_DEFAULT,
    BUNDLE_MIRROR_LOCATION,
    INTENT_TTL_SECONDS,
    QUEUE_SNAPSHOT_HEARTBEAT_TICKS,
    RTMR_INDEX,
    SERVICE_TOKEN as _SERVICE_TOKEN,
    TRUCON_HTTP_PORT as _TRUCON_HTTP_PORT,
    TRUCON_UDS_PATH as _TRUCON_UDS_PATH,
    get_immutable_backend_config,
)
from .immutable_fanout import CompositeImmutableLogAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("trucon")

DEFAULT_CHAIN_ID = "default"


def _require_default_chain_id(chain_id: str) -> str:
    if chain_id != DEFAULT_CHAIN_ID:
        raise HTTPException(status_code=400, detail=f"Only the '{DEFAULT_CHAIN_ID}' measured chain is supported")
    return chain_id


def _openviking_deployment_id(chain_id: str) -> str:
    return os.environ.get("OPENVIKING_CONFIDENTIAL_DEPLOYMENT_ID", f"openviking-{chain_id}")


def _openviking_service_instance_id() -> str:
    return os.environ.get("OPENVIKING_CONFIDENTIAL_SERVICE_INSTANCE_ID", os.environ.get("HOSTNAME", "local-openviking"))


def _openviking_policy_id() -> str:
    return os.environ.get("OPENVIKING_CONFIDENTIAL_POLICY_ID", "openviking-context-send")


def _openviking_policy_version() -> str:
    return os.environ.get("OPENVIKING_CONFIDENTIAL_POLICY_VERSION", "2026-05-25")


def _openviking_egress_mode() -> str:
    return os.environ.get("OPENVIKING_CONFIDENTIAL_EGRESS_MODE", "explicit-allow-required")


def _openviking_privacy_restore_policy() -> str:
    return os.environ.get(
        "OPENVIKING_CONFIDENTIAL_PRIVACY_RESTORE_POLICY",
        "requires-verified-confidential-boundary",
    )


def _json_sha384(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha384:" + hashlib.sha384(encoded).hexdigest()


def _evidence_expiration(generated_at: datetime) -> datetime:
    return generated_at + timedelta(seconds=INTENT_TTL_SECONDS)


def _tdx_environment_hint(message: str) -> str:
    return (
        f"{message}. Check the TDX environment: ensure /dev/tdx_guest is available, "
        "RTMR extend support is exposed, quote generation is functional, and trust-service / attestation configuration is correct"
    )


def _extract_bundle_predicate(bundle_json: str) -> Dict[str, Any]:
    return extract_bundle_predicate(bundle_json)


def _should_extend_rtmr(predicate: Optional[Dict[str, Any]]) -> bool:
    return should_extend_rtmr(predicate)


def _compute_record_lookup_hash(record: Any) -> Optional[str]:
    return compute_record_lookup_hash(record)


def _build_chain_owner_attestation(
    chain_id: str,
    sequence_num: int,
    baseline_rtmr: Optional[str],
    ccel_digest: Optional[str],
    owner_pub_key: str,
) -> Dict[str, Any]:
    quote_adapter = _quote_adapter
    if quote_adapter is None:
        raise HTTPException(status_code=500, detail=_tdx_environment_hint("Quote adapter is unavailable"))

    expected_value = compute_owner_attestation_expected_value(
        chain_id=chain_id,
        sequence_num=sequence_num,
        baseline_rtmr=baseline_rtmr,
        ccel_digest=ccel_digest,
        owner_pub_key=owner_pub_key,
    )

    try:
        quote_material = quote_adapter.quote(expected_value)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_tdx_environment_hint(f"Owner attestation quote acquisition failed: {exc}"),
        ) from exc

    if quote_material.report_data != expected_value:
        raise HTTPException(
            status_code=500,
            detail=_tdx_environment_hint("Owner attestation report data did not match the expected binding value"),
        )

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


def _get_chain_owner_pub_key(chain_id: str) -> Optional[str]:
    return get_chain_owner_pub_key_from_records(get_chain_records(chain_id))


def _build_attested_head_evidence(chain_id: str) -> AttestedHeadEvidence:
    _require_default_chain_id(chain_id)
    state = get_chain_state(chain_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"No chain state for '{chain_id}'")

    confirmed = get_latest_confirmed_record(chain_id)
    if not confirmed or not confirmed["log_id"]:
        raise HTTPException(status_code=409, detail=f"Chain '{chain_id}' has no confirmed immutable-log head")
    if not confirmed["mr_value"]:
        raise HTTPException(status_code=409, detail=f"Chain '{chain_id}' has no measured confirmed head state")
    quote_adapter = _get_quote_adapter()

    expected_value = compute_binding_expected_value(
        chain_id=chain_id,
        sequence_num=confirmed["sequence_num"],
        head_log_id=confirmed["log_id"],
        mr_value=confirmed["mr_value"],
    )

    try:
        quote_material = quote_adapter.quote(expected_value)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=_tdx_environment_hint(f"Quote acquisition failed: {exc}"),
        ) from exc

    if quote_material.report_data != expected_value:
        raise HTTPException(
            status_code=500,
            detail=_tdx_environment_hint("Quote-backed report data did not match the expected binding value"),
        )

    return validate_attested_head_evidence_payload(
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


def _build_openviking_evidence(chain_id: str) -> OpenVikingEvidenceResponse:
    _require_default_chain_id(chain_id)
    attested_evidence = _build_attested_head_evidence(chain_id)
    evidence_payload = attested_evidence.model_dump(mode="json", exclude_none=True)
    generated_at = datetime.now(timezone.utc)
    expires_at = _evidence_expiration(generated_at)
    return OpenVikingEvidenceResponse(
        chain_id=chain_id,
        deployment_id=_openviking_deployment_id(chain_id),
        service_instance_id=_openviking_service_instance_id(),
        tee_type=attested_evidence.tee_type,
        measurement_ref=attested_evidence.mr_value,
        ledger_chain_id=attested_evidence.chain_id,
        ledger_head_id=attested_evidence.head_log_id,
        evidence_digest=_json_sha384(evidence_payload),
        generated_at=generated_at.isoformat(),
        expires_at=expires_at.isoformat(),
        policy_id=_openviking_policy_id(),
        policy_version=_openviking_policy_version(),
        egress_mode=_openviking_egress_mode(),
        privacy_restore_policy=_openviking_privacy_restore_policy(),
        attested_head_evidence=evidence_payload,
    )


def _build_openviking_posture(chain_id: str) -> OpenVikingPostureResponse:
    _require_default_chain_id(chain_id)
    confirmed = get_latest_confirmed_record(chain_id)
    latest_log_id = confirmed["log_id"] if confirmed and "log_id" in confirmed.keys() else None
    now = datetime.now(timezone.utc)
    return OpenVikingPostureResponse(
        chain_id=chain_id,
        deployment_id=_openviking_deployment_id(chain_id),
        service_instance_id=_openviking_service_instance_id(),
        tee_type="tdx",
        policy_id=_openviking_policy_id(),
        policy_version=_openviking_policy_version(),
        egress_mode=_openviking_egress_mode(),
        privacy_restore_policy=_openviking_privacy_restore_policy(),
        generated_at=now.isoformat(),
        has_confirmed_ledger_head=bool(latest_log_id),
        latest_ledger_head_id=latest_log_id,
    )

# ---------------------------------------------------------------------------
# Single-instance file lock
# ---------------------------------------------------------------------------

LOCK_PATH = "/dev/shm/tc_api_queue/trucon.lock"
_lock_fd = None


def _current_lock_path() -> str:
    override = os.environ.get("TRUCON_LOCK_PATH")
    if override:
        return override
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return f"/tmp/trucon-{os.getpid()}.lock"
    return LOCK_PATH

def acquire_instance_lock():
    """Acquire exclusive file lock. Exits if another instance holds it."""
    global _lock_fd
    lock_path = _current_lock_path()
    if _lock_fd is not None:
        logger.info("Single-instance lock already held by this process at %s", lock_path)
        return
    lock_dir = os.path.dirname(lock_path)
    os.makedirs(lock_dir, mode=0o700, exist_ok=True)
    try:
        _lock_fd = open(lock_path, "w")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_fd.write(str(os.getpid()))
        _lock_fd.flush()
        logger.info("Acquired single-instance lock at %s (PID %d)", lock_path, os.getpid())
    except OSError:
        logger.error("Another TruCon instance is already running (lock held at %s)", lock_path)
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


def _load_backend_adapter(backend_name: str, **kwargs) -> ImmutableLogAdapter:
    if backend_name == "rekor":
        return SigstoreLogAdapter(**kwargs)
    if backend_name == "onchain":
        from tlog.backends.onchain.adapter import OnChainLogAdapter

        return OnChainLogAdapter(**kwargs)
    raise ValueError(f"Unknown immutable backend: {backend_name!r}. Supported: rekor, onchain")


def _load_immutable_adapter(**kwargs):
    """Load the configured immutable-log backend adapter."""
    backend_config = get_immutable_backend_config()
    adapters = {
        backend_name: _load_backend_adapter(backend_name, **kwargs)
        for backend_name in backend_config.write_backends
    }
    if len(adapters) == 1:
        return adapters[backend_config.primary_backend]

    secondary_adapters = tuple(
        (backend_name, adapter)
        for backend_name, adapter in adapters.items()
        if backend_name != backend_config.primary_backend
    )
    return CompositeImmutableLogAdapter(
        primary_backend=backend_config.primary_backend,
        primary_adapter=adapters[backend_config.primary_backend],
        secondary_adapters=secondary_adapters,
        write_policy=backend_config.write_policy,
    )
_quote_adapter = None    # Set during lifespan


def _get_quote_adapter() -> TdxQuoteAdapter:
    global _quote_adapter
    if _quote_adapter is None:
        _quote_adapter = TdxQuoteAdapter()
    return _quote_adapter

# RTMR[2] is the default OS/application-layer measurement register in TDX.
# RTMR[0]/[1] are firmware/boot-locked; RTMR[3] can be used for experiments.

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
        logger.error("TDX support incomplete: %s", message)
        raise RuntimeError(_tdx_environment_hint(f"TDX startup requires RTMR extend support; {message}"))

    message = "TDX RTMR sysfs not found and no libtdx_attest extend path is available"
    logger.error("TDX support unavailable: %s", message)
    raise RuntimeError(_tdx_environment_hint(f"TDX startup requires RTMR extend support; {message}"))

# ---------------------------------------------------------------------------
# Submit daemon thread
# ---------------------------------------------------------------------------

_bundle_mirror: Optional[OciBundleMirror] = None
_submit_daemon: Optional[SubmitDaemon] = None
_submit_daemon_thread: Optional[threading.Thread] = None
_last_queue_snapshot: Optional[tuple[int, int, int, int, int]] = None
_last_queue_snapshot_tick = 0
_queue_snapshot_tick = 0


def _extract_confirmed_rekor_identifiers(log_id: str, receipt: Optional[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    return submit_daemon_mod.extract_confirmed_rekor_identifiers(log_id, receipt)


def _compute_bundle_payload_hash(bundle_json: str) -> str:
    return compute_bundle_payload_hash(bundle_json)


def _extract_bundle_payload_b64(bundle_json: str) -> str:
    return extract_bundle_payload_b64(bundle_json)


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


def _emit_queue_snapshot(stats: Dict[str, int]) -> None:
    global _last_queue_snapshot, _last_queue_snapshot_tick, _queue_snapshot_tick

    snapshot = (
        stats["queued_count"],
        stats["submitting_count"],
        stats["failed_retryable_count"],
        stats["failed_terminal_count"],
        stats["total_retry_count"],
    )
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


def _submit_daemon_loop() -> None:
    if _submit_daemon is None:
        raise RuntimeError("Submit daemon is not initialized")
    _submit_daemon.run()


def _submit_daemon_tick() -> None:
    global _submit_daemon
    submit_daemon_mod.get_all_chain_ids = get_all_chain_ids
    submit_daemon_mod.get_failed_by_chain = get_failed_by_chain
    submit_daemon_mod.get_pending_by_chain = get_pending_by_chain
    submit_daemon_mod.set_status_submitting = set_status_submitting
    submit_daemon_mod.update_record_confirmed = update_record_confirmed
    submit_daemon_mod.update_status = update_status
    submit_daemon_mod.update_chain_state = update_chain_state
    submit_daemon_mod.get_queue_stats = get_queue_stats
    if _submit_daemon is None:
        _submit_daemon = SubmitDaemon(
            _immutable_log,
            _bundle_mirror,
            heartbeat_ticks=QUEUE_SNAPSHOT_HEARTBEAT_TICKS,
        )
    _submit_daemon.tick()

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _local_mr, _immutable_log, _quote_adapter, _uds_gateway, _bundle_mirror, _submit_daemon, _submit_daemon_thread, _AUTH_DISABLED

    # Service authentication startup checks
    if _AUTH_DISABLED:
        logger.warning("⚠ TruCon service authentication DISABLED — development mode only")
    elif not _SERVICE_TOKEN and not _TRUCON_UDS_PATH:
        logger.error("Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH is configured while auth is enabled. Refusing to start.")
        raise RuntimeError("Neither TRUCON_SERVICE_TOKEN nor TRUCON_UDS_PATH is configured while auth is enabled")

    # Single-instance enforcement
    acquire_instance_lock()

    # Initialize database
    init_db()

    # Crash recovery
    _crash_recovery()

    # Initialize adapters
    _local_mr = _initialize_local_mr_adapter()

    mirror_location = BUNDLE_MIRROR_LOCATION
    _bundle_mirror = OciBundleMirror(mirror_location) if mirror_location else None
    _immutable_log = _load_immutable_adapter(bundle_mirror=_bundle_mirror)
    _quote_adapter = TdxQuoteAdapter()

    if _TRUCON_UDS_PATH:
        _uds_gateway = TruConUnixSocketGateway(
            socket_path=_TRUCON_UDS_PATH,
            internal_proxy_secret=_INTERNAL_PROXY_SECRET,
            forward_port=_TRUCON_HTTP_PORT,
            auth_disabled=_AUTH_DISABLED,
        )
        _uds_gateway.start()

    _submit_daemon = SubmitDaemon(
        _immutable_log,
        _bundle_mirror,
        heartbeat_ticks=QUEUE_SNAPSHOT_HEARTBEAT_TICKS,
    )
    _submit_daemon_thread = threading.Thread(target=_submit_daemon_loop, daemon=True, name="submit-daemon")
    _submit_daemon_thread.start()

    yield

    # Shutdown
    if _submit_daemon is not None:
        _submit_daemon.stop_event.set()
        if _submit_daemon_thread is not None:
            _submit_daemon_thread.join(timeout=10)
            _submit_daemon_thread = None
        _submit_daemon = None
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

from .routers import query as _query_module
from . import schemas as _schemas_module
from ..identity import sigstore_baseline as _sigstore_baseline_module

app.include_router(_query_module.router)
verify_chain = _query_module.verify_chain
ChainStateResponse = _schemas_module.ChainStateResponse
build_baseline_sigstore_bundle = _sigstore_baseline_module.build_baseline_sigstore_bundle

# ---------------------------------------------------------------------------
# Service authentication middleware
# ---------------------------------------------------------------------------

_AUTH_DISABLED = _AUTH_DISABLED_DEFAULT
_INTERNAL_PROXY_SECRET = secrets.token_urlsafe(32)
_uds_gateway: Optional[TruConUnixSocketGateway] = None


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

        denial = authorize_caller(caller_service, request)
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
    denial = authorize_caller(request.state.caller_service, request)
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
    _require_default_chain_id(chain_id)
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
    _require_default_chain_id(req.chain_id)
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
    _require_default_chain_id(req.chain_id)
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
    _require_default_chain_id(req.chain_id)
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

            should_extend_measurement = _should_extend_rtmr(predicate)
            current_mr_value = state["mr_value"] if state else None
            mr_value, prev_mr_value = current_mr_value, current_mr_value
            if _local_mr and should_extend_measurement:
                try:
                    mr_value, prev_mr_value = _local_mr.extend(RTMR_INDEX, req.event_digest)
                except Exception as e:
                    logger.error("RTMR extend failed: %s", e)
                    raise HTTPException(
                        status_code=500,
                        detail=_tdx_environment_hint(f"RTMR extend failed: {e}"),
                    )

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
                # Keep the record on the durable chain even when this event type
                # intentionally preserves the prior MR value instead of extending.
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

        predicate = None
        try:
            predicate = _extract_bundle_predicate(req.bundle)
        except Exception:
            predicate = None

        # 2. RTMR extend
        should_extend_measurement = _should_extend_rtmr(predicate)
        current_mr_value = state['mr_value'] if state else None
        mr_value, prev_mr_value = current_mr_value, current_mr_value
        if _local_mr and should_extend_measurement:
            try:
                mr_value, prev_mr_value = _local_mr.extend(RTMR_INDEX, req.event_digest)
            except Exception as e:
                logger.error("RTMR extend failed: %s", e)
                raise HTTPException(
                    status_code=500,
                    detail=_tdx_environment_hint(f"RTMR extend failed: {e}"),
                )

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
            # Keep the record on the durable chain even when this event type
            # intentionally preserves the prior MR value instead of extending.
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


@app.get(
    "/evidence",
    response_model=AttestedHeadEvidence,
    responses={404: {"model": EvidenceErrorResponse}, 409: {"model": EvidenceErrorResponse}, 500: {"model": EvidenceErrorResponse}},
)
def get_attested_head_evidence():
    """Return attested-head evidence for the latest confirmed public head of the default measured chain."""
    return _build_attested_head_evidence(DEFAULT_CHAIN_ID)


@app.get(
    "/confidential/evidence",
    response_model=OpenVikingEvidenceResponse,
    responses={404: {"model": EvidenceErrorResponse}, 409: {"model": EvidenceErrorResponse}, 500: {"model": EvidenceErrorResponse}},
)
def get_openviking_confidential_evidence():
    """Return OpenViking-style evidence and trust metadata for context-send verification."""
    return _build_openviking_evidence(DEFAULT_CHAIN_ID)


@app.get(
    "/confidential/posture",
    response_model=OpenVikingPostureResponse,
    responses={404: {"model": EvidenceErrorResponse}},
)
def get_openviking_confidential_posture():
    """Return posture metadata that is separate from attested evidence."""
    state = get_chain_state(DEFAULT_CHAIN_ID)
    if not state:
        raise HTTPException(status_code=404, detail=f"No chain state for '{DEFAULT_CHAIN_ID}'")
    return _build_openviking_posture(DEFAULT_CHAIN_ID)


def main() -> None:
    import uvicorn

    uvicorn.run("tc_api.trucon.app:app", host="0.0.0.0", port=8001, workers=1)


if __name__ == "__main__":
    main()

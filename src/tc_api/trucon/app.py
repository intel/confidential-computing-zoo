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

from .database import (
    DB_PATH,
    delete_non_extended_records,
    get_all_chain_ids,
    get_chain_records,
    get_chain_state,
    get_db_connection,
    get_events_for_instance,
    get_events_for_workload,
    get_failed_by_chain,
    get_highest_extended_record,
    get_instances_for_workload,
    get_latest_confirmed_record,
    get_latest_state,
    get_pending_by_chain,
    get_queue_stats,
    get_record_by_idempotency_key,
    increment_retry,
    init_db,
    insert_record,
    reset_submitting_to_pending,
    set_status_submitting,
    update_chain_state,
    update_record_confirmed,
    update_status,
)
from .adapters.sigstore import SigstoreLogAdapter
from .adapters.ccel import compute_ccel_digest
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("trucon")


def _build_baseline_bundle(chain_id: str, rtmr_value: Optional[str], ccel_digest: Optional[str]) -> tuple[str, str]:
    """Build a DSSE envelope for Event Log 0 using an ephemeral ECDSA P-384 keypair."""
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    private_key = ec.generate_private_key(ec.SECP384R1())
    pub_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    predicate_payload = {
        "event_id": f"evt-log0-{chain_id}",
        "event_type": "chain.init",
        "entries": [
            {"key": "baseline_rtmr", "value": rtmr_value or "null"},
            {"key": "ccel_digest", "value": ccel_digest or "null"},
            {"key": "pub_key", "value": pub_key_pem},
        ],
        "chain_id": chain_id,
    }
    payload_bytes = json.dumps(predicate_payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = base64.b64encode(payload_bytes).decode("utf-8")
    signature = private_key.sign(payload_bytes, ec.ECDSA(hashes.SHA384()))
    sig_b64 = base64.b64encode(signature).decode("utf-8")
    dsse_envelope = json.dumps(
        {
            "payloadType": "application/vnd.dsse+json",
            "payload": payload_b64,
            "signatures": [{"keyid": "", "sig": sig_b64}],
        }
    )
    del private_key
    return dsse_envelope, pub_key_pem


def _create_workload_chain_baseline(chain_id: str, caller_service: Optional[str], auth_transport: Optional[str]) -> None:
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
        signed_bundle, pub_key_pem = _build_baseline_bundle(chain_id, rtmr_value, ccel_digest)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to construct lazy baseline bundle for chain '%s': %s", chain_id, exc)
        raise HTTPException(status_code=500, detail=f"Baseline creation failed: {exc}") from exc

    record_id = str(uuid.uuid4())
    insert_record(
        record_id=record_id,
        event_id=f"evt-log0-{chain_id}",
        payload={
            "bundle": signed_bundle,
            "chain_id": chain_id,
            "pub_key": pub_key_pem,
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
        event_digest=None,
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

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CommitRequest(BaseModel):
    bundle: str          # Signed DSSE bundle JSON string
    chain_id: str        # Chain identifier
    event_digest: str    # SHA-384 digest of the event
    event_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    instance_id: Optional[str] = None

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
    init_token: str

class InitChainRequest(BaseModel):
    chain_id: str
    init_token: str
    signed_bundle: str   # DSSE bundle JSON signed with TEE keypair
    pub_key: str         # ECDSA P-384 public key in PEM format

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
    prev_log_id_ok: Optional[bool] = None
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

# RTMR[2] is the OS/application-layer measurement register in TDX.
# RTMR[0]/[1] are firmware/boot-locked; RTMR[3] is reserved.
RTMR_INDEX = 2

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

# ---------------------------------------------------------------------------
# Submit daemon thread
# ---------------------------------------------------------------------------

_stop_daemon = threading.Event()
MAX_RETRIES = 10
POLL_INTERVAL = 5.0

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
                        logger.info("Record %s confirmed with log_id=%s", record_id, log_id)
                    else:
                        submit_ms = (time.perf_counter() - t_submit) * 1000
                        logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                        _handle_retry(record_id)
                else:
                    # No immutable log backend — mark confirmed (testing/dev)
                    update_record_confirmed(record_id, f"mock-{uuid.uuid4().hex[:8]}")
                    submit_ms = (time.perf_counter() - t_submit) * 1000
                    logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "confirmed")
                    # Emit confirmation_lag if created_at is available
                    created_at = record['created_at'] if 'created_at' in record.keys() else None
                    if created_at:
                        confirmed_at = datetime.utcnow()
                        created_dt = datetime.fromisoformat(created_at)
                        lag_ms = (confirmed_at - created_dt).total_seconds() * 1000
                        logger.info("metric=confirmation_lag lag_ms=%.1f record_id=%s", lag_ms, record_id)
                    logger.info("Record %s mock-confirmed (no immutable log)", record_id)

            except Exception as e:
                submit_ms = (time.perf_counter() - t_submit) * 1000
                logger.info("metric=submit_latency latency_ms=%.1f record_id=%s outcome=%s", submit_ms, record_id, "failed_retryable")
                logger.error("Failed to submit record %s to Rekor: %s", record_id, e)
                _handle_retry(record_id)

    # Emit queue snapshot at end of each tick
    stats = get_queue_stats()
    logger.info(
        "metric=queue_snapshot queue_depth=%d submitting=%d failed_retryable=%d failed_terminal=%d total_retries=%d",
        stats['queued_count'], stats['submitting_count'],
        stats['failed_retryable_count'], stats['failed_terminal_count'],
        stats['total_retry_count'],
    )

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
    global _local_mr, _immutable_log, _quote_adapter, _uds_gateway

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
    try:
        from .adapters.tdx_mr import TdxMRAdapter
        if os.path.exists("/sys/class/misc/tdx_guest/measurements/rtmr"):
            _local_mr = TdxMRAdapter()
            logger.info("TDX RTMR adapter initialized")
        else:
            logger.warning("NON-TEE MODE: TDX RTMR sysfs not found — running without hardware measurement extensions (development/testing only)")
    except Exception as e:
        logger.warning("Could not init local MR adapter: %s", e)

    _immutable_log = SigstoreLogAdapter()
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

        # Compute CCEL digest
        ccel_digest = compute_ccel_digest()

        # Generate init_token
        init_token = secrets.token_urlsafe(32)
        _pending_init_tokens[init_token] = {
            "chain_id": chain_id,
            "rtmr_value": rtmr_value,
            "ccel_digest": ccel_digest,
        }

        return InitChainBaselineResponse(
            rtmr_value=rtmr_value,
            ccel_digest=ccel_digest,
            init_token=init_token,
        )


@app.post("/init-chain", response_model=InitChainResponse)
def init_chain(req: InitChainRequest, request: Request):
    """
    Phase 2 of chain initialization: validate init_token and insert Event Log 0
    (baseline record) into the commit queue.
    """
    with _sequencer_lock:
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

        record_id = str(uuid.uuid4())
        sequence_num = 1

        caller_service = getattr(request.state, "caller_service", None)
        auth_transport = getattr(request.state, "auth_transport", None)

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
                "is_baseline": True,
                "caller_service": caller_service,
                "auth_transport": auth_transport,
            },
            status="PENDING",
            chain_id=req.chain_id,
            rtmr_extended=True,
            prev_log_id=None,
            mr_value=token_data["rtmr_value"],
            sequence_num=sequence_num,
            event_digest=None,
            idempotency_key=f"init-chain-{req.chain_id}",
            instance_id=None,
        )

        # Initialize chain_state
        update_chain_state(
            chain_id=req.chain_id,
            head_record_id=record_id,
            sequence_num=sequence_num,
            mr_value=token_data["rtmr_value"],
        )

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

        # 0.5 Lazy baseline bootstrap for new non-default workload chains
        if req.chain_id != "default" and get_chain_state(req.chain_id) is None:
            _create_workload_chain_baseline(req.chain_id, caller_service, auth_transport)

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
    prev_confirmed_log_id: Optional[str] = None  # tracks preceding confirmed record's log_id
    baseline_error: Optional[str] = None
    # Determine if RTMR is available: at least one non-NULL mr_value
    rtmr_available = any(r['mr_value'] is not None for r in records)

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
        prev_log_id_ok: Optional[bool] = None

        if baseline_error and seq == records[0]['sequence_num']:
            error = baseline_error

        # 1. Sequence continuity check
        if seq != expected_seq:
            error = f"sequence gap: expected {expected_seq}, got {seq}"
            if valid:
                valid = False
                first_error_at = seq

        # 2. RTMR chain integrity check
        if mr_value is None or event_digest is None:
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

        # 4. prev_log_id linkage check (non-TEE fallback)
        if not rtmr_available:
            cur_prev_log_id = r['prev_log_id'] if 'prev_log_id' in r.keys() else None
            if not is_confirmed:
                # Unconfirmed record — cannot verify
                prev_log_id_ok = None
            elif prev_confirmed_log_id is None and cur_prev_log_id is None:
                # First record with no predecessor
                prev_log_id_ok = True
            elif prev_confirmed_log_id is not None and cur_prev_log_id == prev_confirmed_log_id:
                prev_log_id_ok = True
            elif prev_confirmed_log_id is None and cur_prev_log_id is not None:
                # First confirmed record but has a prev_log_id — mismatch
                prev_log_id_ok = False
                link_error = f"prev_log_id mismatch: expected None, got {cur_prev_log_id}"
                error = f"{error}; {link_error}" if error else link_error
                if valid:
                    valid = False
                    first_error_at = seq
            else:
                prev_log_id_ok = False
                link_error = f"prev_log_id mismatch: expected {prev_confirmed_log_id}, got {cur_prev_log_id}"
                error = f"{error}; {link_error}" if error else link_error
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
            prev_log_id_ok=prev_log_id_ok,
            error=error,
        ))

        # Advance state for next iteration
        if mr_value is not None:
            prev_mr = mr_value
        if is_confirmed:
            prev_confirmed_log_id = r['log_id']
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

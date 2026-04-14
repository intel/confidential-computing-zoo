"""
TruCon — Single-instance sequencer for the Trusted Container Log.

Serializes RTMR extend + SQLite INSERT behind a threading.Lock(),
maintains chain state, and embeds a submit daemon as a background thread.

MUST be run with --workers 1 to preserve lock semantics.
"""

import fcntl
import json
import logging
import os
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from trusted_container_log.database import (
    DB_PATH,
    delete_non_extended_records,
    get_all_chain_ids,
    get_chain_state,
    get_failed_by_chain,
    get_highest_extended_record,
    get_pending_by_chain,
    get_queue_stats,
    increment_retry,
    init_db,
    insert_record,
    update_chain_state,
    update_record_confirmed,
    update_status,
)
from trusted_container_log.tlog_impl import SigstoreLogAdapter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s - %(message)s")
logger = logging.getLogger("trucon")

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class CommitRequest(BaseModel):
    bundle: str          # Signed DSSE bundle JSON string
    chain_id: str        # Chain identifier
    event_digest: str    # SHA-384 digest of the event
    event_id: Optional[str] = None

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

class QueueStatusResponse(BaseModel):
    queued_count: int
    failed_count: int
    next_sequence_num: Optional[int] = None

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

# ---------------------------------------------------------------------------
# Crash recovery
# ---------------------------------------------------------------------------

def _crash_recovery():
    """Run on startup: discard non-extended records, rebuild chain_state."""
    deleted = delete_non_extended_records()
    if deleted:
        logger.info("Crash recovery: deleted %d records without RTMR extension", deleted)

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
            min_failed_seq = failed[0]['sequence_num']
        else:
            min_failed_seq = None

        pending = get_pending_by_chain(chain_id)
        for record in pending:
            seq = record['sequence_num']
            # Don't submit past a FAILED record
            if min_failed_seq is not None and seq > min_failed_seq:
                break

            record_id = record['record_id']
            payload = json.loads(record['payload'])
            bundle_json = payload.get('bundle')

            if not bundle_json:
                logger.warning("Record %s has no bundle in payload, skipping", record_id)
                continue

            try:
                from sigstore.models import Bundle
                bundle = Bundle.from_json(bundle_json)

                if _immutable_log:
                    log_id, status, _receipt = _immutable_log.submit_bundle(bundle)
                    if status == "confirmed":
                        update_record_confirmed(record_id, log_id)
                        # Update chain_state head_log_id
                        update_chain_state(
                            chain_id=chain_id,
                            head_record_id=record_id,
                            sequence_num=seq,
                            head_log_id=log_id,
                        )
                        logger.info("Record %s confirmed with log_id=%s", record_id, log_id)
                    else:
                        _handle_retry(record_id)
                else:
                    # No immutable log backend — mark confirmed (testing/dev)
                    update_record_confirmed(record_id, f"mock-{uuid.uuid4().hex[:8]}")
                    logger.info("Record %s mock-confirmed (no immutable log)", record_id)

            except Exception as e:
                logger.error("Failed to submit record %s to Rekor: %s", record_id, e)
                _handle_retry(record_id)

def _handle_retry(record_id: str):
    """Increment retry; transition to FAILED if threshold exceeded."""
    increment_retry(record_id, 'PENDING')
    # Re-read to check current retry_count
    from trusted_container_log.database import get_db_connection
    with get_db_connection() as conn:
        row = conn.execute(
            'SELECT retry_count FROM commit_queue WHERE record_id = ?', (record_id,)
        ).fetchone()
        if row and row['retry_count'] >= MAX_RETRIES:
            update_status(record_id, 'FAILED')
            logger.warning("Record %s moved to FAILED after %d retries", record_id, MAX_RETRIES)

# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _local_mr, _immutable_log

    # Single-instance enforcement
    acquire_instance_lock()

    # Initialize database
    init_db()

    # Crash recovery
    _crash_recovery()

    # Initialize adapters
    try:
        from trusted_container_log.local_mr import TdxMRAdapter
        if os.path.exists("/sys/class/misc/tdx_guest/measurements/rtmr"):
            _local_mr = TdxMRAdapter()
            logger.info("TDX RTMR adapter initialized")
        else:
            logger.info("TDX RTMR sysfs not found, running without local MR extensions")
    except Exception as e:
        logger.warning("Could not init local MR adapter: %s", e)

    _immutable_log = SigstoreLogAdapter()

    # Start submit daemon thread
    daemon_thread = threading.Thread(target=_submit_daemon_loop, daemon=True, name="submit-daemon")
    daemon_thread.start()

    yield

    # Shutdown
    _stop_daemon.set()
    daemon_thread.join(timeout=10)
    release_instance_lock()
    logger.info("TruCon shut down")


app = FastAPI(
    title="TruCon — Trusted Log Sequencer",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/commit", response_model=CommitResponse)
def commit(req: CommitRequest):
    """
    Sequence a signed bundle: RTMR extend + SQLite INSERT + chain_state update.
    All three operations are serialized behind a threading.Lock().
    """
    record_id = str(uuid.uuid4())
    event_id = req.event_id or f"evt-{uuid.uuid4().hex[:8]}"

    with _sequencer_lock:
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
                mr_value, prev_mr_value = _local_mr.extend(0, req.event_digest)
            except Exception as e:
                logger.error("RTMR extend failed: %s", e)
                raise HTTPException(status_code=500, detail=f"RTMR extend failed: {e}")

        # 3. INSERT into commit_queue with rtmr_extended=TRUE
        insert_record(
            record_id=record_id,
            event_id=event_id,
            payload={"bundle": req.bundle, "chain_id": req.chain_id},
            status="PENDING",
            chain_id=req.chain_id,
            rtmr_extended=True,
            prev_log_id=prev_log_id,
            mr_value=mr_value,
            sequence_num=sequence_num,
        )

        # 4. UPDATE chain_state
        update_chain_state(
            chain_id=req.chain_id,
            head_record_id=record_id,
            sequence_num=sequence_num,
            mr_value=mr_value,
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


@app.get("/status", response_model=QueueStatusResponse)
def get_status():
    """Return queue statistics."""
    stats = get_queue_stats()
    return QueueStatusResponse(**stats)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("trucon:app", host="0.0.0.0", port=8001, workers=1)

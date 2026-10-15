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

"""Read-only query endpoints for TruCon."""

from typing import List
import threading

from fastapi import APIRouter, HTTPException

from ..chain_verification import confirmed_chain_state, verify_chain_records
from .. import database as _db
from ..schemas import (
    ChainStateResponse,
    ChainVerificationResponse,
    CommitQueueStatusResponse,
    EventSummary,
    InstanceSummary,
    LatestStateResponse,
)

router = APIRouter()

DEFAULT_CHAIN_ID = "default"
MAX_HISTORY_ENTRIES = 4096
sequencer_lock = threading.Lock()


@router.get("/chain-state", response_model=ChainStateResponse, response_model_exclude_unset=True)
def get_chain_state_endpoint(include_history: bool = False):
    """Return chain state, optionally requiring complete confirmed history.

    History mode returns a consistent head and its ordered log references, or
    409 while any record is unconfirmed. References retain the backend's format.
    """
    # Same lock as mutation reservation and commit in the service. The returned
    # view linearizes before a new reservation can be acknowledged to Docktap.
    with sequencer_lock:
        return _chain_state(include_history)


def _chain_state(include_history):
    # Even the old head is unsafe to report while Docker may have changed
    # without a confirmed lifecycle record describing the outcome.
    if _db.has_unresolved_docktap_mutation(DEFAULT_CHAIN_ID):
        raise HTTPException(status_code=409, detail='Docker mutation has no confirmed lifecycle record',
                            headers={'X-Argus-Reason': 'MUTATION_PENDING'})
    if include_history:
        # Read one extra row to reject overflow, never silently return a
        # truncated prefix as the complete history needed for RTMR2 replay.
        rows = _db.get_chain_records(DEFAULT_CHAIN_ID, limit=MAX_HISTORY_ENTRIES + 1, metadata_only=True)
        try:
            return confirmed_chain_state(DEFAULT_CHAIN_ID, rows, MAX_HISTORY_ENTRIES)
        except ValueError as exc:
            reason = 'HISTORY_CAPACITY' if len(rows) > MAX_HISTORY_ENTRIES else 'HISTORY_NOT_CONFIRMED'
            raise HTTPException(status_code=409, detail=str(exc), headers={'X-Argus-Reason': reason}) from exc
    state = _db.get_chain_state(DEFAULT_CHAIN_ID)
    if not state:
        raise HTTPException(status_code=404, detail=f"No chain state for '{DEFAULT_CHAIN_ID}'",
                            headers={'X-Argus-Reason': 'HISTORY_MISSING'})
    return ChainStateResponse(
        chain_id=DEFAULT_CHAIN_ID,
        head_record_id=state['head_record_id'],
        head_log_id=state['head_log_id'],
        sequence_num=state['sequence_num'],
        mr_value=state['mr_value'],
        updated_at=state['updated_at'],
    )


@router.get("/status", response_model=CommitQueueStatusResponse)
def get_status():
    """Return queue statistics matching CommitQueueStatus contract."""
    stats = _db.get_queue_stats()
    return CommitQueueStatusResponse(
        has_queued_records=stats['queued_count'] > 0,
        queued_record_count=stats['queued_count'],
        next_record_id=stats.get('next_record_id'),
        submitting_count=stats['submitting_count'],
        failed_retryable_count=stats['failed_retryable_count'],
        failed_terminal_count=stats['failed_terminal_count'],
        total_retry_count=stats['total_retry_count'],
    )


@router.get("/state", response_model=LatestStateResponse)
def get_state():
    """Return LatestState for the default chain."""
    state = _db.get_latest_state(DEFAULT_CHAIN_ID)
    return LatestStateResponse(**state)


@router.get("/verify-chain", response_model=ChainVerificationResponse)
def verify_chain():
    """Return full chain traversal verification for the default measured chain."""
    return verify_chain_records(DEFAULT_CHAIN_ID, records=_db.get_chain_records(DEFAULT_CHAIN_ID))


@router.get("/workloads/{workload_id}/instances", response_model=List[InstanceSummary])
def list_workload_instances(workload_id: str):
    """List all container instances for a workload."""
    rows = _db.get_instances_for_workload(workload_id)
    return [InstanceSummary(**row) for row in rows]


@router.get("/instances/{instance_id}/events", response_model=List[EventSummary])
def list_instance_events(instance_id: str):
    """List all events for a specific container instance."""
    rows = _db.get_events_for_instance(instance_id)
    return [EventSummary(**row) for row in rows]


@router.get("/workloads/{workload_id}/events", response_model=List[EventSummary])
def list_workload_events(workload_id: str):
    """List all events across all instances of a workload."""
    rows = _db.get_events_for_workload(workload_id)
    return [EventSummary(**row) for row in rows]

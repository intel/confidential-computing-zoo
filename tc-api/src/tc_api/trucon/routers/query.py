"""Read-only query endpoints for TruCon."""

from typing import List

from fastapi import APIRouter, HTTPException

from ..chain_verification import verify_chain_records
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


@router.get("/chain-state/{chain_id}", response_model=ChainStateResponse)
def get_chain_state_endpoint(chain_id: str):
    """Return current chain state for a given chain_id."""
    state = _db.get_chain_state(chain_id)
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
    state = _db.get_latest_state('default')
    return LatestStateResponse(**state)


@router.get("/verify-chain/{chain_id}", response_model=ChainVerificationResponse)
def verify_chain(chain_id: str):
    """Return full chain traversal verification for a chain."""
    return verify_chain_records(chain_id, records=_db.get_chain_records(chain_id))


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

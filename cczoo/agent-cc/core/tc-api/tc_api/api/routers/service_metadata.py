"""
Service Metadata Router - Provides service information to argus evidence engine

This router exposes internal endpoints for querying service metadata that is
used by the argus evidence engine to generate binding claims for TDX attestation.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..request_auth import enforce_authenticated_request
from ...docktap.workload_store import WorkloadStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/service-metadata", tags=["service-metadata"])


class ServiceMetadataResponse(BaseModel):
    """Response model for service metadata queries."""

    workload_id: str
    container_id: Optional[str] = None
    launch_id: Optional[str] = None
    image_digest: Optional[str] = None
    service_name: Optional[str] = None
    created_at: Optional[str] = None
    last_seen_at: Optional[str] = None


class WorkloadQueryRequest(BaseModel):
    """Request model for workload queries by container or workload ID."""

    container_id: Optional[str] = None
    workload_id: Optional[str] = None


def get_workload_store() -> WorkloadStore:
    """Get the workload store instance. Requires init_db() called first."""
    store = WorkloadStore()
    store.init_db()
    return store


@router.post("/workload/query", response_model=ServiceMetadataResponse)
async def query_workload_metadata(
    request: WorkloadQueryRequest,
    _auth: Any = Depends(enforce_authenticated_request),
) -> ServiceMetadataResponse:
    """
    Query service metadata by container_id or workload_id.

    This endpoint is used by the argus evidence engine to retrieve service
    metadata for generating binding claims during TDX attestation.

    Args:
        request: Query request with either container_id or workload_id
        _auth: Authentication dependency (enforced)

    Returns:
        ServiceMetadataResponse with service metadata

    Raises:
        HTTPException: If no query parameter provided or not found
    """
    store = get_workload_store()

    if not request.container_id and not request.workload_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either container_id or workload_id must be provided",
        )

    try:
        if request.container_id:
            metadata = store.get_workload_by_container(request.container_id)
        elif request.workload_id:
            metadata = store.get_workload_by_id(request.workload_id)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either container_id or workload_id must be provided",
            )

        if not metadata:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workload not found for query: {request.container_id or request.workload_id}",
            )

        return ServiceMetadataResponse(**metadata)

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error querying workload metadata: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error querying workload metadata: {exc}",
        )


@router.get("/health")
async def service_metadata_health() -> Dict[str, str]:
    """
    Health check endpoint for service metadata router.

    Returns:
        Dict with health status
    """
    return {"status": "healthy", "router": "service-metadata"}


# Export the router
__all__ = ["router"]
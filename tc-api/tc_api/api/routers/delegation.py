from fastapi import APIRouter

from .. import delegation_support


router = APIRouter()


@router.post("/api/docktap/delegate", response_model=delegation_support.DelegateResponse)
async def docktap_delegate(request: delegation_support.DelegateRequest):
    return await delegation_support.docktap_delegate(request=request)

from fastapi import APIRouter

from .. import lunks_support


router = APIRouter()


@router.post("/api/create_lunks", response_model=lunks_support.CreateLunksRespone)
async def create_lunks(request: lunks_support.CreateLunksRequest):
    from ..app import app

    return await lunks_support.create_lunks(request=request, trusted_log=app.state.trusted_log)


@router.post("/api/mount_lunks", response_model=lunks_support.MountLunksRespone)
async def mount_lunks(request: lunks_support.MountLunksRequest):
    from ..app import app

    return await lunks_support.mount_lunks(request=request, trusted_log=app.state.trusted_log)


@router.post("/api/unmount_lunks", response_model=lunks_support.UnmountLunksRespone)
async def unmount_lunks(request: lunks_support.UnmountLunksRequest):
    from ..app import app

    return await lunks_support.unmount_lunks(request=request, trusted_log=app.state.trusted_log)


@router.get("/api/lunks-result/{user_id}", response_model=lunks_support.LunksResult)
async def get_lunks_result(user_id: str):
    return await lunks_support.get_lunks_result(user_id=user_id)

from fastapi import APIRouter

from .. import luks_support


router = APIRouter()


@router.post("/api/create_luks", response_model=luks_support.CreateLuksResponse)
async def create_luks(request: luks_support.CreateLuksRequest):
    from ..app import app

    return await luks_support.create_luks(request=request, trusted_log=app.state.trusted_log)


@router.post("/api/mount_luks", response_model=luks_support.MountLuksResponse)
async def mount_luks(request: luks_support.MountLuksRequest):
    from ..app import app

    return await luks_support.mount_luks(request=request, trusted_log=app.state.trusted_log)


@router.post("/api/unmount_luks", response_model=luks_support.UnmountLuksResponse)
async def unmount_luks(request: luks_support.UnmountLuksRequest):
    from ..app import app

    return await luks_support.unmount_luks(request=request, trusted_log=app.state.trusted_log)


@router.get("/api/luks-result/{user_id}", response_model=luks_support.LuksResult)
async def get_luks_result(user_id: str):
    return await luks_support.get_luks_result(user_id=user_id)

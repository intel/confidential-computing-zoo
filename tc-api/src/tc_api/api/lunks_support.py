from fastapi import HTTPException

from tlog.types import Entry

from ..identity.sigstore_identity import resolve_sigstore_identity_token
from ..models import (
    CreateLunksRequest,
    CreateLunksRespone,
    LunksResult,
    MountLunksRequest,
    MountLunksRespone,
    UnmountLunksRequest,
    UnmountLunksRespone,
)
from .runtime import docker_service, logger


async def create_lunks(request: CreateLunksRequest, trusted_log):
    try:
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        logger.info("Create Lunks block file for user: %s", request.user_id)

        trusted_log.add_entry(record_id, Entry(key="lunks", value={"lunks": "Start creating lunks blocks"}))
        mapdir, loopdevice = docker_service.create_lunks_block(
            request.user_id,
            trusted_log,
            request.passwd,
            request.vfs_size,
            request.vfs_path,
        )

        identity_token = resolve_sigstore_identity_token("create_lunks", logger=logger, allow_interactive=False)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("create_lunks", "", trusted_log, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "creating lunks block", "")
            if tlog_status:
                logger.info("Save create_lunks transparency success.")
            else:
                logger.info("Save create_lunks transparency failed.")
            verify_tlog_status = docker_service.verify_chain_state("create_lunks", trusted_log)
        else:
            verify_tlog_status = "skipped"

        docker_service.update_lunks_status(
            request.user_id,
            "create success",
            step="create_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return CreateLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=mapdir,
            vfs_path=request.vfs_path,
            loop_device=loopdevice,
            vfs_size=request.vfs_size,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create lunks: {exc}") from exc


async def mount_lunks(request: MountLunksRequest, trusted_log):
    try:
        logger.info("Mount Lunks block file for user: %s", request.user_id)
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        status = "failed"
        docker_service.mount_lunks_block(
            request.user_id,
            trusted_log,
            request.mapper_dir,
            request.passwd,
            request.mount_path,
            request.vfs_path,
            request.loop_device,
        )

        identity_token = resolve_sigstore_identity_token("mount_lunks", logger=logger, allow_interactive=False)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("mount_lunks", "", trusted_log, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "mount_lunks block", "")
            if tlog_status:
                logger.info("Save build transparency success.")
            else:
                logger.info("Save build transparency failed.")
            verify_tlog_status = docker_service.verify_chain_state("mount_lunks", trusted_log)
        else:
            verify_tlog_status = "skipped"

        if verify_tlog_status == "success":
            status = "mount_lunks success"

        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="mount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return MountLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=request.mapper_dir,
            vfs_path=request.vfs_path,
            loop_device=request.loop_device,
            mount_path=request.mount_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to mount lunks: {exc}") from exc


async def unmount_lunks(request: UnmountLunksRequest, trusted_log):
    try:
        logger.info("Umount Lunks block file for user: %s", request.user_id)
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        status = "failed"
        docker_service.unmount_lunks_block(request.user_id, trusted_log, request.mapper_dir, request.mount_path, request.loop_device)

        identity_token = resolve_sigstore_identity_token("unmount_lunks", logger=logger, allow_interactive=False)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("unmount_lunks", "", trusted_log, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "unmount_lunks block", "")
            if tlog_status:
                logger.info("Save build transparency success.")
            else:
                logger.info("Save build transparency failed.")
            verify_tlog_status = docker_service.verify_chain_state("unmount_lunks", trusted_log)
        else:
            verify_tlog_status = "skipped"

        if verify_tlog_status == "success":
            status = "unmount_lunks success"
        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="unmount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return UnmountLunksRespone(
            user_id=request.user_id,
            mapper_dir=request.mapper_dir,
            loop_device=request.loop_device,
            mount_path=request.mount_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unmount lunks: {exc}") from exc


async def get_lunks_result(user_id: str):
    try:
        lunks = docker_service.get_lunks_status(user_id)
        if not lunks:
            raise HTTPException(status_code=404, detail="User not found")
        return lunks
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get lunks result: {exc}") from exc


__all__ = [
    "CreateLunksRequest",
    "CreateLunksRespone",
    "LunksResult",
    "MountLunksRequest",
    "MountLunksRespone",
    "UnmountLunksRequest",
    "UnmountLunksRespone",
    "create_lunks",
    "docker_service",
    "get_lunks_result",
    "mount_lunks",
    "unmount_lunks",
]
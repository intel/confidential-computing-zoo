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

from fastapi import HTTPException, Request

from tlog.types import Entry

from ..models import (
    CreateLuksRequest,
    CreateLuksResponse,
    LuksResult,
    MountLuksRequest,
    MountLuksResponse,
    UnmountLuksRequest,
    UnmountLuksResponse,
)
from .request_auth import add_authenticated_identity_entries, get_authenticated_caller, require_authenticated_owner
from .runtime import docker_service, logger


def _commit_luks_receipt(operation: str, user_id: str, identity_token: str, trusted_log, record_id: str, transparency_step: str):
    tlog_status, tlog_id = docker_service.commit_and_save_receipt(operation, "", trusted_log, record_id, identity_token)
    docker_service.update_transparencylog_status(user_id, str(tlog_id), transparency_step, "")
    if tlog_status:
        logger.info("Save %s transparency success.", operation)
    else:
        logger.info("Save %s transparency failed.", operation)
    return tlog_id, docker_service.verify_chain_state(operation, trusted_log)


async def create_luks(http_request: Request, request: CreateLuksRequest, trusted_log):
    try:
        caller = get_authenticated_caller(
            "create_luks",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        logger.info("Create LUKS block file for user: %s", request.user_id)
        add_authenticated_identity_entries(trusted_log, record_id, caller)

        trusted_log.add_entry(record_id, Entry(key="luks", value={"luks": "Start creating LUKS block"}))
        mapdir, loopdevice = docker_service.create_luks_block(
            request.user_id,
            trusted_log,
            record_id,
            request.passwd,
            request.vfs_size,
            request.vfs_path,
        )

        tlog_id, verify_tlog_status = _commit_luks_receipt(
            "create_luks",
            request.user_id,
            caller.identity_token,
            trusted_log,
            record_id,
            "creating luks block",
        )

        docker_service.update_luks_status(
            request.user_id,
            "create success",
            step="create_luks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return CreateLuksResponse(
            user_id=request.user_id,
            mapper_dir=mapdir,
            vfs_path=request.vfs_path,
            loop_device=loopdevice,
            vfs_size=request.vfs_size,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create luks: {exc}") from exc


async def mount_luks(http_request: Request, request: MountLuksRequest, trusted_log):
    try:
        caller = get_authenticated_caller(
            "mount_luks",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        logger.info("Mount LUKS block file for user: %s", request.user_id)
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        status = "failed"
        add_authenticated_identity_entries(trusted_log, record_id, caller)
        mount_path, loop_device = docker_service.mount_luks_block(
            request.user_id,
            trusted_log,
            record_id,
            request.mapper_dir,
            request.passwd,
            request.mount_path,
            request.vfs_path,
            request.loop_device,
        )
        tlog_id, verify_tlog_status = _commit_luks_receipt(
            "mount_luks",
            request.user_id,
            caller.identity_token,
            trusted_log,
            record_id,
            "mount_luks block",
        )

        if verify_tlog_status == "success":
            status = "mount_luks success"

        docker_service.update_luks_status(
            request.user_id,
            status,
            step="mount_luks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return MountLuksResponse(
            user_id=request.user_id,
            mapper_dir=request.mapper_dir,
            vfs_path=request.vfs_path,
            loop_device=loop_device,
            mount_path=mount_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to mount luks: {exc}") from exc


async def unmount_luks(http_request: Request, request: UnmountLuksRequest, trusted_log):
    try:
        caller = get_authenticated_caller(
            "unmount_luks",
            request=http_request,
            user_id=request.user_id,
            identity_token=request.identity_token,
        )
        request.user_id = caller.user_id
        request.identity_token = caller.identity_token
        logger.info("Unmount LUKS block file for user: %s", request.user_id)
        ctx = trusted_log.init_record()
        record_id = ctx.record_id
        status = "failed"
        add_authenticated_identity_entries(trusted_log, record_id, caller)
        docker_service.unmount_luks_block(request.user_id, trusted_log, record_id, request.mapper_dir, request.mount_path, request.loop_device)

        tlog_id, verify_tlog_status = _commit_luks_receipt(
            "unmount_luks",
            request.user_id,
            caller.identity_token,
            trusted_log,
            record_id,
            "unmount_luks block",
        )

        if verify_tlog_status == "success":
            status = "unmount_luks success"
        docker_service.update_luks_status(
            request.user_id,
            status,
            step="unmount_luks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status,
        )
        return UnmountLuksResponse(
            user_id=request.user_id,
            mapper_dir=request.mapper_dir,
            loop_device=request.loop_device,
            mount_path=request.mount_path,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to unmount luks: {exc}") from exc


async def get_luks_result(http_request: Request, user_id: str):
    try:
        luks = docker_service.get_luks_status(user_id)
        if not luks:
            raise HTTPException(status_code=404, detail="User not found")
        return luks
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get luks result: {exc}") from exc


__all__ = [
    "CreateLuksRequest",
    "CreateLuksResponse",
    "LuksResult",
    "MountLuksRequest",
    "MountLuksResponse",
    "UnmountLuksRequest",
    "UnmountLuksResponse",
    "create_luks",
    "docker_service",
    "get_luks_result",
    "mount_luks",
    "unmount_luks",
]
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

from datetime import datetime

from fastapi import HTTPException

from ..models import GetTransparencyRequest, SummaryTransparencyResponse, TransparencyResult
from .runtime import docker_service, logger


async def root():
    logger.info("Health check request received")
    return {"message": "TC API Service is running", "timestamp": datetime.now()}


async def get_transparency_log(log_id: str):
    try:
        tlog_result = docker_service.get_transparencyLog_status(log_id)
        if not tlog_result:
            raise HTTPException(status_code=404, detail="Transparency log not found")
        return tlog_result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get transparency log result: {exc}") from exc


async def get_summary_transparencylog(request: GetTransparencyRequest):
    try:
        result = await docker_service.get_summaryTransparencylog(request.build_id, request.launch_id)
        if not result:
            raise HTTPException(status_code=404, detail="Launch not found")
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get launch result: {exc}") from exc


__all__ = [
    "SummaryTransparencyResponse",
    "TransparencyResult",
    "get_summary_transparencylog",
    "get_transparency_log",
    "root",
]
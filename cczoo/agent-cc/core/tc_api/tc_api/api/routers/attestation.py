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

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, field_validator

from ...trucon.adapters.tdx_quote import TdxQuoteAdapter


logger = logging.getLogger(__name__)

router = APIRouter(tags=["attestation"])


class TdxQuoteRequest(BaseModel):
    workload_id: Optional[str] = None
    report_data: str

    @field_validator("report_data")
    @classmethod
    def validate_report_data(cls, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise ValueError("report_data must be a non-empty hex string")
        try:
            bytes.fromhex(normalized)
        except ValueError as exc:
            raise ValueError("report_data must be valid hex") from exc
        return normalized


class TdxQuoteResponse(BaseModel):
    workload_id: str
    quote: str
    report_data: str
    quote_format: Optional[str] = None


@router.post("/v1/attestation", response_model=TdxQuoteResponse)
async def generate_tdx_quote(request: TdxQuoteRequest) -> TdxQuoteResponse:
    adapter = TdxQuoteAdapter()
    expected_value = f"sha384:{request.report_data}"

    try:
        quote_material = adapter.quote(expected_value)
    except Exception as exc:
        logger.error("Failed to generate TDX quote for workload %s: %s", request.workload_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate TDX quote: {exc}",
        ) from exc

    return TdxQuoteResponse(
        workload_id=request.workload_id or "unknown",
        quote=quote_material.quote,
        report_data=request.report_data,
        quote_format=quote_material.quote_format,
    )


__all__ = ["router"]
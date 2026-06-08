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

from fastapi import APIRouter, Request

from .. import delegation_support


router = APIRouter()


@router.post("/api/docktap/delegate", response_model=delegation_support.DelegateResponse)
async def docktap_delegate(http_request: Request, request: delegation_support.DelegateRequest):
    return await delegation_support.docktap_delegate(request=request, http_request=http_request)


@router.post("/api/docktap/authorize", response_model=delegation_support.DocktapAuthorizationResponse)
async def docktap_authorization_ready(http_request: Request, request: delegation_support.DocktapAuthorizationRequest):
    return await delegation_support.docktap_authorization_ready(request=request, http_request=http_request)

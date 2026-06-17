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

from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse


def authorize_caller(caller_service: str, request: Request) -> Optional[JSONResponse]:
    if caller_service in {"auth_bypass", "compat_http", "tc_api"}:
        return None

    if caller_service == "docktap":
        if request.method == "POST" and request.url.path in {"/commit", "/commit-intents/reserve", "/init-chain"}:
            return None
        if request.method == "GET" and request.url.path.startswith("/init-chain/") and request.url.path.endswith("/baseline"):
            return None
        return JSONResponse(
            status_code=403,
            content={"detail": f"Caller '{caller_service}' is not authorized for {request.method} {request.url.path}"},
        )

    return JSONResponse(status_code=401, content={"detail": "Unrecognized caller identity"})
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

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .. import sigstore_support as support

router = APIRouter()

router.add_api_route(
    "/api/sigstore/interactive-login",
    support.sigstore_interactive_login,
    methods=["GET"],
    response_class=HTMLResponse,
)
router.add_api_route(
    "/api/sigstore/identity-token",
    support.sigstore_identity_token,
    methods=["GET"],
)
router.add_api_route(
    "/api/sigstore/login-status/{session_id}",
    support.sigstore_login_status,
    methods=["GET"],
)
router.add_api_route(
    "/api/sigstore/callback",
    support.sigstore_identity_callback,
    methods=["GET"],
    response_class=HTMLResponse,
)
router.add_api_route(
    "/api/sigstore/identity-token",
    support.sigstore_identity_token_complete,
    methods=["POST"],
)

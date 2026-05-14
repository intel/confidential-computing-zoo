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

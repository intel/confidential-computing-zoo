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
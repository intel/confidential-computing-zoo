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
from dataclasses import dataclass
import json
from typing import Optional

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from ..identity.oidc_preflight import inspect_identity_token
from ..identity.sigstore_identity import resolve_sigstore_identity_token


logger = logging.getLogger(__name__)


_PROTECTED_OPERATION_PATHS = {
    ("POST", "/api/build-package"): "build",
    ("POST", "/api/publish-package"): "publish",
    ("POST", "/api/deploy-launch"): "launch",
    ("POST", "/api/create_luks"): "create_luks",
    ("POST", "/api/mount_luks"): "mount_luks",
    ("POST", "/api/unmount_luks"): "unmount_luks",
    ("POST", "/api/docktap/delegate"): "docktap_delegate",
    ("POST", "/api/docktap/authorize"): "docktap_authorize",
}

_OPERATIONS_WITH_OPTIONAL_USER_BINDING = {
    "docktap_delegate",
    "docktap_authorize",
}


@dataclass(frozen=True)
class AuthenticatedCaller:
    operation: str
    user_id: str
    identity_token: str
    derived_identity: str
    subject: Optional[str]
    issuer: Optional[str]
    email: Optional[str]


def _resolve_bearer_token(request: Optional[Request]) -> Optional[str]:
    if request is None:
        return None
    authorization = request.headers.get("Authorization")
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authorization scheme, expected Bearer")
    token = token.strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    return token


def authenticate_request_identity(
    operation: str,
    *,
    user_id: Optional[str],
    identity_token: Optional[str],
    request: Optional[Request] = None,
    enforce_user_binding: bool = False,
    allow_cached_token: bool = False,
) -> AuthenticatedCaller:
    claimed_user_id = user_id.strip() if isinstance(user_id, str) else ""
    header_token = _resolve_bearer_token(request)
    if header_token and identity_token and header_token != identity_token:
        raise HTTPException(
            status_code=400,
            detail="Authorization bearer token must match identity_token when both are provided",
        )

    explicit_token = header_token or identity_token
    effective_token = explicit_token
    if not effective_token and allow_cached_token:
        effective_token = resolve_sigstore_identity_token(
            operation,
            allow_interactive=False,
            min_ttl_seconds=0,
            require_token=False,
        )

    if not effective_token:
        raise HTTPException(
            status_code=400,
            detail={
                "error": f"Sigstore identity token is required for {operation}.",
                "operation": operation,
                "message": "Provide a caller identity_token in the request body or as an Authorization: Bearer token.",
            },
        )

    expected_identity = (claimed_user_id or None) if enforce_user_binding else None
    token_report = inspect_identity_token(effective_token, expected_identity=expected_identity)
    if not token_report.get("valid_for_sigstore"):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "identity_token is not valid for Sigstore",
                "operation": operation,
                "issues": token_report.get("errors") or ["Sigstore identity parsing failed"],
            },
        )

    derived_identity = token_report.get("derived_identity")
    if not derived_identity:
        raise HTTPException(
            status_code=401,
            detail={
                "error": "identity_token did not yield a signer identity",
                "operation": operation,
            },
        )

    if token_report.get("errors"):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "identity_token failed request identity validation",
                "operation": operation,
                "issues": token_report["errors"],
                "derived_identity": derived_identity,
                "claimed_user_id": claimed_user_id,
            },
        )

    if not enforce_user_binding and claimed_user_id and claimed_user_id != derived_identity:
        logger.warning(
            "Ignoring caller-supplied user_id %r for %s; using authenticated identity %r",
            claimed_user_id,
            operation,
            derived_identity,
        )

    return AuthenticatedCaller(
        operation=operation,
        user_id=derived_identity,
        identity_token=effective_token,
        derived_identity=derived_identity,
        subject=token_report.get("subject"),
        issuer=token_report.get("issuer"),
        email=token_report.get("email"),
    )


def add_authenticated_identity_entries(tlog, record_id: str, caller: AuthenticatedCaller) -> None:
    from tlog.types import Entry

    tlog.add_entry(
        record_id,
        Entry(
            key="authenticated_identity",
            value={
                "operation": caller.operation,
                "user_id": caller.user_id,
                "derived_identity": caller.derived_identity,
                "subject": caller.subject,
                "issuer": caller.issuer,
                "email": caller.email,
            },
        ),
    )


def authenticated_operation_for_request(request: Request) -> Optional[str]:
    return _PROTECTED_OPERATION_PATHS.get((request.method.upper(), request.url.path))


def get_authenticated_caller(
    operation: str,
    *,
    request: Optional[Request],
    user_id: Optional[str],
    identity_token: Optional[str],
) -> AuthenticatedCaller:
    if request is not None:
        caller = getattr(request.state, "authenticated_caller", None)
        if caller is not None and caller.operation == operation:
            return caller
    return authenticate_request_identity(
        operation,
        user_id=user_id,
        identity_token=identity_token,
        request=request,
        enforce_user_binding=False,
        allow_cached_token=True,
    )


def require_authenticated_owner(
    operation: str,
    *,
    request: Request,
    owner_user_id: str,
) -> AuthenticatedCaller:
    return authenticate_request_identity(
        operation,
        user_id=owner_user_id,
        identity_token=None,
        request=request,
        enforce_user_binding=True,
        allow_cached_token=False,
    )


async def enforce_authenticated_request(request: Request) -> Optional[JSONResponse]:
    operation = authenticated_operation_for_request(request)
    if operation is None:
        return None

    body = await request.body()

    async def _receive():
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive

    try:
        payload = json.loads(body.decode("utf-8") or "{}") if body else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    user_id = payload.get("user_id")
    if not isinstance(user_id, str) or not user_id.strip():
        user_id = ""

    identity_token = payload.get("identity_token")
    if identity_token is not None and not isinstance(identity_token, str):
        identity_token = None

    try:
        request.state.authenticated_caller = authenticate_request_identity(
            operation,
            user_id=user_id,
            identity_token=identity_token,
            request=request,
            enforce_user_binding=False,
            allow_cached_token=True,
        )
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    return None


__all__ = [
    "AuthenticatedCaller",
    "add_authenticated_identity_entries",
    "authenticated_operation_for_request",
    "enforce_authenticated_request",
    "authenticate_request_identity",
    "get_authenticated_caller",
    "require_authenticated_owner",
]
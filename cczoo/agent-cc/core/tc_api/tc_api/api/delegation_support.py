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

from typing import List, Optional

from fastapi import HTTPException, Request
from pydantic import BaseModel

from .request_auth import get_authenticated_caller
from .runtime import TRUCON_URL, logger
from ..docktap import config as docktap_cfg


class DelegateRequest(BaseModel):
    chain_id: str
    identity_token: Optional[str] = None
    scope: Optional[List[str]] = None
    ttl_seconds: Optional[int] = None


class DelegateResponse(BaseModel):
    delegation_id: str
    expires_at: str
    chain_id: str
    scope: List[str]


class DocktapAuthorizationRequest(BaseModel):
    chain_id: Optional[str] = None
    identity_token: Optional[str] = None


class DocktapAuthorizationResponse(BaseModel):
    ready: bool
    auth_mode: str
    chain_id: str
    scope: List[str]
    expires_at: Optional[str] = None
    delegation_id: Optional[str] = None
    source: str
    detail: Optional[str] = None


def _resolve_chain_id(chain_id: Optional[str]) -> str:
    return docktap_cfg.RUNTIME_CHAIN_ID


def _policy_scope() -> List[str]:
    return list(docktap_cfg.delegation_scope())


def _scope_satisfies_policy(scope: List[str], required_scope: List[str]) -> bool:
    return set(required_scope).issubset(set(scope))


def _build_authorization_response(
    *,
    ready: bool,
    chain_id: str,
    source: str,
    scope: Optional[List[str]] = None,
    expires_at: Optional[str] = None,
    delegation_id: Optional[str] = None,
    detail: Optional[str] = None,
) -> DocktapAuthorizationResponse:
    return DocktapAuthorizationResponse(
        ready=ready,
        auth_mode=docktap_cfg.auth_mode(),
        chain_id=chain_id,
        scope=list(scope or _policy_scope()),
        expires_at=expires_at,
        delegation_id=delegation_id,
        source=source,
        detail=detail,
    )


async def docktap_delegate(request: DelegateRequest, http_request: Optional[Request] = None):
    caller = get_authenticated_caller(
        "docktap_delegate",
        request=http_request,
        user_id="",
        identity_token=request.identity_token,
    )
    identity_token_str = caller.identity_token
    request.identity_token = identity_token_str

    from tc_api.docktap.trucon_client import TruConCommitter

    committer = TruConCommitter(trucon_url=TRUCON_URL, start_retry_worker=False)
    try:
        result = committer.submit_delegation(
            chain_id=request.chain_id,
            identity_token_str=identity_token_str,
            scope=request.scope,
            ttl_seconds=request.ttl_seconds,
        )
    except Exception as exc:
        logger.error("Delegation creation failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DelegateResponse(**result)


async def docktap_authorization_ready(request: DocktapAuthorizationRequest, http_request: Optional[Request] = None) -> DocktapAuthorizationResponse:
    caller = get_authenticated_caller(
        "docktap_authorize",
        request=http_request,
        user_id="",
        identity_token=request.identity_token,
    )

    from tc_api.docktap.trucon_client import TruConCommitter
    from tc_api.trucon.database import get_active_delegation

    chain_id = _resolve_chain_id(request.chain_id)
    required_scope = _policy_scope()

    try:
        delegation = get_active_delegation(chain_id)
    except Exception:
        delegation = None

    if delegation is not None and _scope_satisfies_policy(delegation["scope"], required_scope):
        return _build_authorization_response(
            ready=True,
            chain_id=chain_id,
            source="existing_delegation",
            scope=delegation["scope"],
            expires_at=delegation.get("expires_at"),
            delegation_id=delegation.get("delegation_id"),
        )

    if not docktap_cfg.delegation_required():
        return _build_authorization_response(
            ready=True,
            chain_id=chain_id,
            source="identity_token",
        )

    committer = TruConCommitter(trucon_url=TRUCON_URL, start_retry_worker=False)
    try:
        result = committer.submit_delegation(
            chain_id=chain_id,
            identity_token_str=caller.identity_token,
            scope=None,
            ttl_seconds=None,
        )
    except Exception as exc:
        logger.error("Docktap authorization readiness failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _build_authorization_response(
        ready=True,
        chain_id=chain_id,
        source="created_delegation",
        scope=result.get("scope", required_scope),
        expires_at=result.get("expires_at"),
        delegation_id=result.get("delegation_id"),
    )


__all__ = [
    "DelegateRequest",
    "DelegateResponse",
    "DocktapAuthorizationRequest",
    "DocktapAuthorizationResponse",
    "docktap_authorization_ready",
    "docktap_delegate",
]
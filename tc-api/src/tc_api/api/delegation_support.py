from typing import List, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from ..identity.sigstore_identity import resolve_sigstore_identity_token
from .runtime import TRUCON_URL, logger


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


async def docktap_delegate(request: DelegateRequest):
    identity_token_str = request.identity_token
    if not identity_token_str:
        identity_token_str = resolve_sigstore_identity_token(
            "docktap",
            logger=logger,
            allow_interactive=False,
            require_token=False,
        )
    if not identity_token_str:
        raise HTTPException(status_code=401, detail="No OIDC identity token available. Please log in first.")

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


__all__ = ["DelegateRequest", "DelegateResponse", "docktap_delegate"]
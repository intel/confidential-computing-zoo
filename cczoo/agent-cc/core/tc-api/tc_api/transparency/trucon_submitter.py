from typing import Any, Dict, Optional

from ..trucon.internal_transport import request_json


def reserve_commit_intent(
    *,
    trucon_url: str,
    caller_service: str,
    chain_id: str,
    idempotency_key: Optional[str] = None,
    is_baseline: bool = False,
    timeout: int = 30,
) -> Dict[str, Any]:
    return request_json(
        "POST",
        "/commit-intents/reserve",
        json_body={
            "chain_id": chain_id,
            "idempotency_key": idempotency_key,
            "is_baseline": is_baseline,
        },
        caller_service=caller_service,
        timeout=timeout,
        trucon_url=trucon_url,
    )


def post_commit_to_trucon(
    *,
    trucon_url: str,
    caller_service: str,
    bundle_json: str,
    chain_id: str,
    event_digest: str,
    event_id: str,
    intent_token: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    instance_id: Optional[str] = None,
    identity_token: Optional[str] = None,
    owner_authorization: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    payload = {
        "bundle": bundle_json,
        "chain_id": chain_id,
        "event_digest": event_digest,
        "event_id": event_id,
        "intent_token": intent_token,
        "idempotency_key": idempotency_key,
        "instance_id": instance_id,
        "identity_token": identity_token,
        "owner_authorization": owner_authorization,
    }
    return request_json(
        "POST",
        "/commit",
        json_body=payload,
        caller_service=caller_service,
        timeout=timeout,
        trucon_url=trucon_url,
    )


__all__ = ["post_commit_to_trucon", "reserve_commit_intent"]
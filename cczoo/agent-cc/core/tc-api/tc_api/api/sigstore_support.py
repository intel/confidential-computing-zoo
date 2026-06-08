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

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from html import escape
from typing import Any, Optional
import threading
from datetime import datetime
import json
import logging
import requests
import urllib.parse
import uuid
from pydantic import BaseModel
from ..identity.oidc_preflight import inspect_identity_token
from ..identity.sigstore_oauth import (
    SIGSTORE_OIDC_CLIENT_ID,
    SIGSTORE_OIDC_CLIENT_SECRET,
    SIGSTORE_OIDC_ISSUER_URL,
    SIGSTORE_OIDC_SESSION_TTL_SECONDS,
    SIGSTORE_OOB_REDIRECT_URI,
    build_sigstore_pkce_pair as _build_sigstore_pkce_pair,
    get_sigstore_issuer as _get_sigstore_issuer,
    normalize_sigstore_login_flow as _normalize_sigstore_login_flow,
    sigstore_provider_callback_base_url as _sigstore_provider_callback_base_url,
)
from ..identity.sigstore_identity import MissingSigstoreIdentityTokenError, cache_sigstore_identity_token, resolve_sigstore_identity_token
from .sigstore_templates import render_callback_page, render_interactive_login_page

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("tuf.api._payload").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

_sigstore_login_sessions: dict[str, dict[str, Any]] = {}
_sigstore_login_results: dict[str, dict[str, Any]] = {}
_sigstore_login_sessions_lock = threading.Lock()


class SigstoreIdentityTokenExchangeRequest(BaseModel):
    operation: str
    session_id: str
    verification_code: Optional[str] = None
    redirect_url: Optional[str] = None

def _sigstore_interactive_login_path(operation: str, session_id: Optional[str] = None) -> str:
    query = {"operation": operation}
    if session_id:
        query["session_id"] = session_id
    return f"/api/sigstore/interactive-login?{urllib.parse.urlencode(query)}"

def _sigstore_interactive_token_path(operation: str, force_oob: bool = False) -> str:
    suffix = "&force_oob=true" if force_oob else ""
    return f"/api/sigstore/identity-token?operation={operation}{suffix}"

def _sigstore_callback_path() -> str:
    return "/api/sigstore/callback"

def _sigstore_login_status_path(session_id: str) -> str:
    return f"/api/sigstore/login-status/{urllib.parse.quote(session_id)}"

def _sigstore_login_flow_query(flow: str) -> str:
    return urllib.parse.urlencode({"flow": flow})

def _sigstore_interactive_token_flow_path(operation: str, flow: str) -> str:
    return f"/api/sigstore/identity-token?operation={urllib.parse.quote(operation)}&{_sigstore_login_flow_query(flow)}"

def _absolute_request_url(request: Request, path: str) -> str:
    return str(request.base_url).rstrip("/") + path

def _sigstore_session_now_epoch() -> int:
    return int(datetime.utcnow().timestamp())

def _prune_sigstore_login_sessions(now_epoch: Optional[int] = None) -> None:
    current_time = now_epoch if now_epoch is not None else _sigstore_session_now_epoch()
    expired_ids = [
        session_id
        for session_id, session in _sigstore_login_sessions.items()
        if int(session["expires_at_epoch"]) <= current_time
    ]
    for session_id in expired_ids:
        _sigstore_login_sessions.pop(session_id, None)
    expired_result_ids = [
        session_id
        for session_id, result in _sigstore_login_results.items()
        if int(result["expires_at_epoch"]) <= current_time
    ]
    for session_id in expired_result_ids:
        _sigstore_login_results.pop(session_id, None)

def _sigstore_redirect_uri_for_flow(request: Request, flow: str, force_oob: bool = False) -> str:
    if force_oob or flow == "oob":
        return SIGSTORE_OOB_REDIRECT_URI
    if flow == "server-callback":
        return str(request.url_for("sigstore_identity_callback"))
    return _sigstore_provider_callback_base_url()

def _store_sigstore_login_session(
    operation: str,
    issuer: Any,
    auth_url: str,
    state: str,
    code_verifier: str,
    redirect_uri: str,
    flow: str,
) -> dict[str, Any]:
    now_epoch = _sigstore_session_now_epoch()
    session = {
        "session_id": uuid.uuid4().hex,
        "operation": operation,
        "issuer": getattr(issuer, "oidc_config", None).authorization_endpoint if getattr(issuer, "oidc_config", None) else SIGSTORE_OIDC_ISSUER_URL,
        "token_endpoint": issuer.oidc_config.token_endpoint,
        "state": state,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "flow": flow,
        "auth_url": auth_url,
        "created_at_epoch": now_epoch,
        "expires_at_epoch": now_epoch + SIGSTORE_OIDC_SESSION_TTL_SECONDS,
    }
    with _sigstore_login_sessions_lock:
        _prune_sigstore_login_sessions(now_epoch)
        _sigstore_login_sessions[session["session_id"]] = session
    return session

def _start_sigstore_login(operation: str, request: Request, flow: str = "copy-url", force_oob: bool = False) -> dict[str, Any]:
    normalized_flow = _normalize_sigstore_login_flow(flow)
    cached_token = resolve_sigstore_identity_token(
        operation,
        logger=logger,
        allow_interactive=False,
        min_ttl_seconds=0,
        suppress_warning=True,
    )
    if cached_token:
        token_report = inspect_identity_token(cached_token)
        return {
            "operation": operation,
            "status": "token_ready",
            "source": "cache",
            "identity_token": cached_token,
            "derived_identity": token_report.get("derived_identity"),
            "federated_issuer": token_report.get("federated_issuer"),
            "expires_at": token_report.get("expires_at"),
            "expires_in_seconds": token_report.get("expires_in_seconds"),
            "interactive_login_url": _sigstore_interactive_login_path(operation),
        }

    issuer = _get_sigstore_issuer()
    code_verifier, code_challenge = _build_sigstore_pkce_pair()
    state = str(uuid.uuid4())
    redirect_uri = _sigstore_redirect_uri_for_flow(request, normalized_flow, force_oob=force_oob)
    auth_params = {
        "response_type": "code",
        "client_id": SIGSTORE_OIDC_CLIENT_ID,
        "client_secret": SIGSTORE_OIDC_CLIENT_SECRET,
        "scope": "openid email",
        "redirect_uri": redirect_uri,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    auth_url = f"{issuer.oidc_config.authorization_endpoint}?{urllib.parse.urlencode(auth_params)}"
    session = _store_sigstore_login_session(
        operation,
        issuer,
        auth_url,
        state,
        code_verifier,
        redirect_uri,
        normalized_flow,
    )
    if normalized_flow == "oob" or force_oob:
        message = (
            "Open auth_url in a browser. After sign-in, Sigstore will show a verification code. Copy that code and submit it back to the server to finish token exchange."
        )
        completion_hint = "copy the verification code and submit it back to the server"
    elif normalized_flow == "copy-url":
        message = (
            "Open auth_url in a browser. After sign-in, the browser will land on a URL that starts with "
            "https://oauth2.sigstore.dev/auth/callback. Copy that full URL and submit it back to the server so it can finish token exchange automatically."
        )
        completion_hint = "copy the final browser URL and submit it back to the server"
    else:
        message = (
            "Open auth_url in a browser. After sign-in, Sigstore will redirect back to the server callback page, which will finish token exchange automatically."
        )
        completion_hint = "let the browser redirect back to the server callback page"
    return {
        "operation": operation,
        "status": "browser_login_pending",
        "flow": normalized_flow,
        "session_id": session["session_id"],
        "auth_url": auth_url,
        "state": state,
        "redirect_uri": redirect_uri,
        "expires_at": datetime.utcfromtimestamp(session["expires_at_epoch"]).isoformat() + "Z",
        "message": message,
        "completion_hint": completion_hint,
        "interactive_login_url": _sigstore_interactive_login_path(operation),
        "callback_url": _sigstore_callback_path(),
        "sigstore_callback_url": _sigstore_provider_callback_base_url(),
    }

def _get_sigstore_login_session(session_id: str) -> dict[str, Any]:
    with _sigstore_login_sessions_lock:
        _prune_sigstore_login_sessions()
        session = _sigstore_login_sessions.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail={
            "error": "Sigstore login session was not found or has expired.",
            "session_id": session_id,
        })
    return session

def _get_sigstore_login_session_by_state(state: str) -> dict[str, Any]:
    with _sigstore_login_sessions_lock:
        _prune_sigstore_login_sessions()
        for session in _sigstore_login_sessions.values():
            if session["state"] == state:
                return session
    raise HTTPException(
        status_code=404,
        detail={
            "error": "Sigstore login session was not found or has expired.",
            "state": state,
        },
    )

def _get_sigstore_login_status(session_id: str) -> dict[str, Any]:
    with _sigstore_login_sessions_lock:
        _prune_sigstore_login_sessions()
        completed = _sigstore_login_results.get(session_id)
        if completed is not None:
            return {key: value for key, value in completed.items() if key != "expires_at_epoch"}
        session = _sigstore_login_sessions.get(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "Sigstore login session was not found or has expired.",
                "session_id": session_id,
            },
        )
    return {
        "operation": session["operation"],
        "status": "browser_login_pending",
        "flow": session.get("flow"),
        "session_id": session_id,
        "auth_url": session.get("auth_url"),
        "redirect_uri": session.get("redirect_uri"),
        "expires_at": datetime.utcfromtimestamp(session["expires_at_epoch"]).isoformat() + "Z",
        "interactive_login_url": _sigstore_interactive_login_path(session["operation"], session_id=session_id),
    }

def _exchange_sigstore_verification_code(
    operation: str,
    session_id: str,
    verification_code: str,
) -> dict[str, Any]:
    session = _get_sigstore_login_session(session_id)
    if session["operation"] != operation:
        raise HTTPException(status_code=400, detail={
            "error": "Sigstore login session does not match the requested operation.",
            "session_id": session_id,
            "operation": operation,
        })

    response = requests.post(
        session["token_endpoint"],
        data={
            "grant_type": "authorization_code",
            "redirect_uri": session["redirect_uri"],
            "code": verification_code.strip(),
            "code_verifier": session["code_verifier"],
        },
        auth=(SIGSTORE_OIDC_CLIENT_ID, SIGSTORE_OIDC_CLIENT_SECRET),
        timeout=30,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        raise HTTPException(status_code=400, detail={
            "error": "Sigstore token exchange failed.",
            "session_id": session_id,
            "operation": operation,
            "message": f"Token request failed with {response.status_code}",
        }) from exc

    token_json = response.json()
    token_error = token_json.get("error")
    if token_error is not None:
        raise HTTPException(status_code=400, detail={
            "error": "Sigstore token exchange failed.",
            "session_id": session_id,
            "operation": operation,
            "message": f"Error response from token endpoint: {token_error}",
        })

    identity_token = str(token_json["access_token"]).strip()
    cache_sigstore_identity_token(identity_token, logger=logger)
    token_report = inspect_identity_token(identity_token)
    result = {
        "operation": operation,
        "status": "token_ready",
        "session_id": session_id,
        "identity_token": identity_token,
        "source": "verification_code",
        "derived_identity": token_report.get("derived_identity"),
        "federated_issuer": token_report.get("federated_issuer"),
        "expires_at": token_report.get("expires_at"),
        "expires_in_seconds": token_report.get("expires_in_seconds"),
        "interactive_login_url": _sigstore_interactive_login_path(operation),
    }
    with _sigstore_login_sessions_lock:
        _sigstore_login_sessions.pop(session_id, None)
        _sigstore_login_results[session_id] = {
            **result,
            "expires_at_epoch": session["expires_at_epoch"],
        }
    return result

def _complete_sigstore_login_from_redirect_url(
    operation: str,
    session_id: str,
    redirect_url: str,
) -> dict[str, Any]:
    session = _get_sigstore_login_session(session_id)
    if session["operation"] != operation:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Sigstore login session does not match the requested operation.",
                "session_id": session_id,
                "operation": operation,
            },
        )

    parsed = urllib.parse.urlparse(redirect_url.strip())
    expected_prefix = _sigstore_provider_callback_base_url()
    actual_prefix = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    if actual_prefix != expected_prefix:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Redirect URL must come from the Sigstore provider callback page.",
                "expected_prefix": expected_prefix,
                "received_prefix": actual_prefix,
            },
        )

    query = urllib.parse.parse_qs(parsed.query)
    code = (query.get("code") or [""])[0].strip()
    state = (query.get("state") or [""])[0].strip()
    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Redirect URL must include both code and state.",
                "redirect_url": redirect_url,
            },
        )
    if state != session["state"]:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Sigstore redirect URL state does not match the login session.",
                "session_id": session_id,
            },
        )

    return _exchange_sigstore_verification_code(operation, session_id, code)

def _missing_sigstore_identity_detail(operation: str, request: Optional[Request] = None) -> dict:
    detail = {
        "error": f"Sigstore identity token is required for {operation}.",
        "operation": operation,
        "message": "Open the interactive login URL or auth_url and complete Sigstore sign-in in your browser. In SSH/remote environments, copy the final browser URL that starts with https://oauth2.sigstore.dev/auth/callback and submit it back to the server so it can finish token exchange automatically.",
        "open_in_browser_url": None,
        "after_login_open_url": None,
        "login_status_url": None,
        "paste_back_url_prefix": _sigstore_provider_callback_base_url(),
        "next_steps": [
            "Open after_login_open_url in your browser to continue Sigstore login.",
            "Use the browser page to complete login instead of pasting URLs back into the terminal.",
            "The client can poll login_status_url and retry automatically once the token is ready.",
        ],
        "interactive_login_url": _sigstore_interactive_login_path(operation),
        "interactive_token_url": _sigstore_interactive_token_flow_path(operation, "copy-url"),
        "interactive_callback_url": _sigstore_callback_path(),
        "sigstore_callback_url": _sigstore_provider_callback_base_url(),
    }

    if request is None:
        return detail

    try:
        login = _start_sigstore_login(operation, request, flow="copy-url")
    except Exception as exc:
        logger.warning("Failed to pre-create Sigstore login session for %s: %s", operation, exc)
        return detail

    detail.update(
        {
            "open_in_browser_url": login.get("auth_url"),
            "auth_url": login.get("auth_url"),
            "session_id": login.get("session_id"),
            "redirect_uri": login.get("redirect_uri"),
            "state": login.get("state"),
            "expires_at": login.get("expires_at"),
            "callback_url": login.get("callback_url"),
            "flow": login.get("flow"),
            "login_status": login.get("status"),
            "complete_login_url": "/api/sigstore/identity-token",
            "login_status_url": _sigstore_login_status_path(str(login.get("session_id") or "")),
            "interactive_continue_url": _sigstore_interactive_login_path(
                operation, session_id=login.get("session_id")
            ),
        }
    )
    detail["after_login_open_url"] = _absolute_request_url(
        request,
        detail["interactive_continue_url"],
    )
    if login.get("flow") == "copy-url":
        detail["message"] = (
            "Open auth_url in a browser. After sign-in, copy the final browser URL that starts with "
            "https://oauth2.sigstore.dev/auth/callback and submit it back to the server so it can finish token "
            "exchange automatically and show the identity_token for retry."
        )
    else:
        detail["message"] = (
            "Open auth_url in a browser. After sign-in, Sigstore will redirect through its callback flow and then back "
            "to the server callback page, which will finish token exchange automatically and show the identity_token for retry."
        )
    return detail

def _resolve_required_sigstore_identity_token(
    operation: str,
    supplied_token: Optional[str],
    request: Optional[Request] = None,
) -> str:
    if supplied_token:
        return supplied_token

    try:
        identity_token = resolve_sigstore_identity_token(
            operation,
            logger=logger,
            min_ttl_seconds=0,
            require_token=True,
        )
    except MissingSigstoreIdentityTokenError as exc:
        raise HTTPException(status_code=400, detail=_missing_sigstore_identity_detail(operation, request=request)) from exc

    if not identity_token:
        raise HTTPException(status_code=400, detail=_missing_sigstore_identity_detail(operation, request=request))
    return identity_token

__all__ = [
    'sigstore_identity_callback',
    'sigstore_identity_token',
    'sigstore_identity_token_complete',
    'sigstore_interactive_login',
    'sigstore_login_status',
    'SigstoreIdentityTokenExchangeRequest',
    '_sigstore_interactive_login_path',
    '_sigstore_interactive_token_path',
    '_sigstore_callback_path',
    '_sigstore_login_status_path',
    '_sigstore_provider_callback_base_url',
    '_sigstore_login_flow_query',
    '_sigstore_interactive_token_flow_path',
    '_absolute_request_url',
    '_sigstore_session_now_epoch',
    '_prune_sigstore_login_sessions',
    '_get_sigstore_issuer',
    '_build_sigstore_pkce_pair',
    '_normalize_sigstore_login_flow',
    '_sigstore_redirect_uri_for_flow',
    '_store_sigstore_login_session',
    '_start_sigstore_login',
    '_get_sigstore_login_session',
    '_get_sigstore_login_session_by_state',
    '_get_sigstore_login_status',
    '_exchange_sigstore_verification_code',
    '_complete_sigstore_login_from_redirect_url',
    '_missing_sigstore_identity_detail',
    '_resolve_required_sigstore_identity_token',
]

async def sigstore_interactive_login(operation: str = "build", session_id: Optional[str] = None):
    safe_operation = escape(operation, quote=True)
    remote_token_url = escape(_sigstore_interactive_token_flow_path(operation, "copy-url"), quote=True)
    callback_token_url = escape(_sigstore_interactive_token_flow_path(operation, "server-callback"), quote=True)
    oob_token_url = escape(_sigstore_interactive_token_path(operation, force_oob=True), quote=True)
    submit_url = escape("/api/sigstore/identity-token", quote=True)
    existing_session: Optional[dict[str, Any]] = None
    if session_id:
        try:
            existing_session = _get_sigstore_login_session(session_id)
        except HTTPException:
            existing_session = None
    initial_status = "Idle"
    initial_auth_url = "Not started"
    initial_session_id = ""
    initial_flow = "copy-url"
    if existing_session:
        initial_status = json.dumps(
            {
                "status": "browser_login_pending",
                "flow": existing_session.get("flow"),
                "session_id": existing_session.get("session_id"),
                "auth_url": existing_session.get("auth_url"),
            },
            indent=2,
        )
        initial_auth_url = str(existing_session.get("auth_url") or "Not started")
        initial_session_id = str(existing_session.get("session_id") or "")
        initial_flow = str(existing_session.get("flow") or "copy-url")
    sample_payload = escape(
        '{"dockerfile":"FROM ghcr.io/1186258278/openclaw-zh:nightly","app_binary":"dGVzdCBiaW5hcnkK","configs":["Y29uZmlnCg=="],"data":["ZGF0YQo="],"encrypt":true,"user_id":"test-user","identity_token":"<paste token here>"}',
        quote=False,
    )
    return HTMLResponse(
        content=render_interactive_login_page(
            safe_operation=safe_operation,
            remote_token_url=remote_token_url,
            callback_token_url=callback_token_url,
            oob_token_url=oob_token_url,
            submit_url=submit_url,
            initial_status=initial_status,
            initial_auth_url=initial_auth_url,
            initial_session_id=initial_session_id,
            initial_flow=initial_flow,
            sample_payload=sample_payload,
            initial_session_id_json=json.dumps(initial_session_id or None),
            initial_flow_json=json.dumps(initial_flow if initial_session_id else None),
        )
    )

async def sigstore_identity_token(request: Request, operation: str = "build", flow: str = "copy-url", force_oob: bool = False):
    try:
        effective_flow = "oob" if force_oob else flow
        return _start_sigstore_login(operation, request, flow=effective_flow, force_oob=force_oob)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "error": f"Failed to start Sigstore OIDC login for {operation}.",
                "operation": operation,
                "message": str(exc),
                "interactive_login_url": _sigstore_interactive_login_path(operation),
            },
        ) from exc

async def sigstore_login_status(session_id: str):
    return _get_sigstore_login_status(session_id)

async def sigstore_identity_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    payload: dict[str, Any]
    if error:
        payload = {
            "sigstore_login_result": True,
            "status": "error",
            "error": "Sigstore login failed.",
            "message": error,
        }
    elif not code or not state:
        payload = {
            "sigstore_login_result": True,
            "status": "error",
            "error": "Sigstore callback is missing required parameters.",
            "message": "Expected both code and state in the callback URL.",
        }
    else:
        try:
            session = _get_sigstore_login_session_by_state(state)
            exchange = _exchange_sigstore_verification_code(
                operation=session["operation"],
                session_id=session["session_id"],
                verification_code=code,
            )
            payload = {
                "sigstore_login_result": True,
                **exchange,
            }
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
            payload = {
                "sigstore_login_result": True,
                "status": "error",
                **detail,
            }

    payload_json = json.dumps(payload).replace("</", "<\\/")
    title = "Sigstore Login Complete" if payload.get("status") == "token_ready" else "Sigstore Login Failed"
    return HTMLResponse(
        content=render_callback_page(title=title, payload_json=payload_json)
    )

async def sigstore_identity_token_complete(request: SigstoreIdentityTokenExchangeRequest):
    if request.redirect_url:
        return _complete_sigstore_login_from_redirect_url(
            operation=request.operation,
            session_id=request.session_id,
            redirect_url=request.redirect_url,
        )
    if request.verification_code:
        return _exchange_sigstore_verification_code(
            operation=request.operation,
            session_id=request.session_id,
            verification_code=request.verification_code,
        )
    raise HTTPException(
        status_code=400,
        detail={
            "error": "Either redirect_url or verification_code is required to complete Sigstore login.",
            "session_id": request.session_id,
        },
    )


from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from html import escape
from typing import Any, List, Optional
import os
import uuid
import asyncio
import tempfile
import base64
import threading
from datetime import datetime
import json
import shutil
import logging
import hashlib
import pickle
import requests
import urllib.parse
from pydantic import BaseModel
from ..trust.commit_client import TrustedLogAPI
from tlog.types import Entry
from ..models import *
from ..services import DockerService
from ..kbs_service import KBSService
from ..identity.oidc_preflight import inspect_identity_token
from ..identity.sigstore_identity import MissingSigstoreIdentityTokenError, cache_sigstore_identity_token, resolve_sigstore_identity_token
from ..config import (
    HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR,
    DOCKER_REGISTRY, DOCKER_REPOSITORY, ENABLE_TDX, TRUCON_URL,
    INIT_DEFAULT_CHAIN_ON_STARTUP,
    TRANSPARENCY_SERVICE_CHAIN_ID,
    TRANSPARENCY_WORKLOAD_CHAIN_PREFIX,
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logging.getLogger("tuf.api._payload").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

SIGSTORE_OIDC_ISSUER_URL = os.environ.get("TC_API_SIGSTORE_OIDC_ISSUER", "https://oauth2.sigstore.dev/auth")
SIGSTORE_OIDC_CLIENT_ID = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_ID", "sigstore")
SIGSTORE_OIDC_CLIENT_SECRET = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_SECRET", "")
SIGSTORE_OIDC_SESSION_TTL_SECONDS = max(60, int(os.environ.get("TC_API_SIGSTORE_OIDC_SESSION_TTL_SECONDS", "600")))
SIGSTORE_OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"
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

def _sigstore_provider_callback_base_url() -> str:
    return urllib.parse.urljoin(SIGSTORE_OIDC_ISSUER_URL.rstrip("/") + "/", "callback")

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

def _get_sigstore_issuer():
    from sigstore.oidc import Issuer

    production = getattr(Issuer, "production", None)
    if callable(production):
        return production()
    return Issuer(SIGSTORE_OIDC_ISSUER_URL)

def _build_sigstore_pkce_pair() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("utf-8")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")
    return code_verifier, code_challenge

def _normalize_sigstore_login_flow(flow: Optional[str]) -> str:
    normalized = (flow or "copy-url").strip().lower()
    if normalized in {"copy-url", "copy_url", "remote", "ssh", "provider-callback"}:
        return "copy-url"
    if normalized in {"server-callback", "server_callback", "callback", "direct"}:
        return "server-callback"
    if normalized in {"oob", "verification-code", "verification_code", "device"}:
        return "oob"
    raise HTTPException(
        status_code=400,
        detail={
            "error": "Unsupported Sigstore login flow.",
            "supported_flows": ["copy-url", "server-callback", "oob"],
            "received": flow,
        },
    )

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
        content=f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>Sigstore OIDC Login</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem auto; max-width: 860px; line-height: 1.5; }}
        textarea, pre {{ width: 100%; box-sizing: border-box; }}
        textarea {{ min-height: 12rem; }}
        <button type="button" onclick="startLogin('server-callback')">Start Direct Callback Login</button>
        button {{ margin-right: 0.75rem; margin-bottom: 0.75rem; padding: 0.6rem 1rem; }}
    <h2>Status</h2>
    <pre id="status">{escape(initial_status, quote=False)}</pre>
<body>
    <pre id="auth_url">{escape(initial_auth_url, quote=False)}</pre>
    <p>This page helps you obtain a short-lived OIDC token for the <strong>{safe_operation}</strong> operation without setting any environment variables.</p>
    <p>If you came here from a missing-token API response, this page can continue the same login session without making you assemble a JSON request manually.</p>
    <p>Choose the login mode that matches your environment. Use SSH/Remote Mode when your browser cannot reach this server directly after login. Use Direct Callback Mode only when your browser can open this server's callback URL.</p>
    <p>
        <button type=\"button\" onclick=\"startLogin('copy-url')\">Start SSH/Remote Login</button>
    <pre id="status">{escape(initial_status, quote=False)}</pre>
    <p>
    <pre id="auth_url">{escape(initial_auth_url, quote=False)}</pre>
        <button type="button" onclick="startLogin('oob')">Start OOB Login</button>
    <pre id=\"status\">Idle</pre>
    <h2>Login URL</h2>
    <pre id=\"auth_url\">Not started</pre>
    <h2>Final Browser URL</h2>
    <textarea id=\"redirect_url\" spellcheck=\"false\" placeholder=\"For SSH/Remote Mode: after login, paste the final browser URL that starts with https://oauth2.sigstore.dev/auth/callback here\"></textarea>
    <p>
        <button type=\"button\" onclick=\"completeRemoteLogin()\">Submit Final URL</button>
    </p>
    <h2>Identity Token</h2>
    <textarea id=\"token\" spellcheck=\"false\" placeholder=\"Token will appear here after login completes\"></textarea>
    <h2>Verification Code</h2>
    <textarea id="verification_code" spellcheck="false" placeholder="For OOB Mode: paste the verification code shown by Sigstore here"></textarea>
    <p>
        <button type="button" onclick="completeOobLogin()">Submit Verification Code</button>
    </p>
    <h2>Retry Example</h2>
    <pre id=\"retry\">curl -X POST \"http://127.0.0.1:8000/api/build-package\" -H \"Content-Type: application/json\" -d '{sample_payload}'</pre>
    <script>
        let pendingSessionId = {json.dumps(initial_session_id or None)};
        let pendingFlow = {json.dumps(initial_flow if initial_session_id else None)};

        function updateRetry(identityToken) {{
            const retry = document.getElementById('retry');
            retry.textContent = 'curl -X POST "http://127.0.0.1:8000/api/build-package" -H "Content-Type: application/json" -d ' + JSON.stringify({{
                dockerfile: 'FROM ghcr.io/1186258278/openclaw-zh:nightly',
                app_binary: 'dGVzdCBiaW5hcnkK',
                configs: ['Y29uZmlnCg=='],
                data: ['ZGF0YQo='],
                encrypt: true,
                user_id: 'test-user',
                identity_token: identityToken,
            }});
        }}

        window.addEventListener('message', (event) => {{
            if (event.origin !== window.location.origin) {{
                return;
            }}
            if (!event.data || event.data.sigstore_login_result !== true) {{
                return;
            }}
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            status.textContent = JSON.stringify(event.data, null, 2);
            if (event.data.status === 'token_ready') {{
                tokenBox.value = event.data.identity_token;
                updateRetry(event.data.identity_token);
            }}
        }});

        async function startLogin(flow) {{
            const status = document.getElementById('status');
            const authUrl = document.getElementById('auth_url');
            const tokenBox = document.getElementById('token');
            const redirectUrl = document.getElementById('redirect_url');
            status.textContent = 'Starting Sigstore OIDC login...';
            tokenBox.value = '';
            redirectUrl.value = '';
            try {{
                let loginUrl = '{remote_token_url}';
                if (flow === 'server-callback') {{
                    loginUrl = '{callback_token_url}';
                }} else if (flow === 'oob') {{
                    loginUrl = '{oob_token_url}';
                }}
                const response = await fetch(loginUrl);
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                if (data.status === 'token_ready') {{
                    tokenBox.value = data.identity_token;
                    status.textContent = JSON.stringify(data, null, 2);
                    authUrl.textContent = 'Used cached token';
                    updateRetry(data.identity_token);
                    return;
                }}
                pendingSessionId = data.session_id;
                pendingFlow = data.flow;
                authUrl.textContent = data.auth_url;
                status.textContent = JSON.stringify(data, null, 2);
                window.open(data.auth_url, '_blank', 'noopener');
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}

        async function completeRemoteLogin() {{
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            const redirectUrl = document.getElementById('redirect_url').value.trim();
            if (!pendingSessionId) {{
                status.textContent = 'Start a login flow first to create a Sigstore session.';
                return;
            }}
            if (pendingFlow !== 'copy-url') {{
                status.textContent = 'The current session expects automatic server callback. Start SSH/Remote Login to use pasted final URLs.';
                return;
            }}
            if (!redirectUrl) {{
                status.textContent = 'Paste the final browser URL before submitting.';
                return;
            }}
            status.textContent = 'Finishing Sigstore login from the pasted browser URL...';
            try {{
                const response = await fetch('{submit_url}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        operation: '{safe_operation}',
                        session_id: pendingSessionId,
                        redirect_url: redirectUrl,
                    }}),
                }});
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                tokenBox.value = data.identity_token;
                status.textContent = JSON.stringify(data, null, 2);
                updateRetry(data.identity_token);
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}

        async function completeOobLogin() {{
            const status = document.getElementById('status');
            const tokenBox = document.getElementById('token');
            const verificationCode = document.getElementById('verification_code').value.trim();
            if (!pendingSessionId) {{
                status.textContent = 'Start a login flow first to create a Sigstore session.';
                return;
            }}
            if (pendingFlow !== 'oob') {{
                status.textContent = 'The current session is not using OOB. Start OOB Login to use verification codes.';
                return;
            }}
            if (!verificationCode) {{
                status.textContent = 'Paste the verification code before submitting.';
                return;
            }}
            status.textContent = 'Finishing Sigstore login from the pasted verification code...';
            try {{
                const response = await fetch('{submit_url}', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        operation: '{safe_operation}',
                        session_id: pendingSessionId,
                        verification_code: verificationCode,
                    }}),
                }});
                const data = await response.json();
                if (!response.ok) {{
                    status.textContent = JSON.stringify(data, null, 2);
                    return;
                }}
                tokenBox.value = data.identity_token;
                status.textContent = JSON.stringify(data, null, 2);
                updateRetry(data.identity_token);
            }} catch (error) {{
                status.textContent = String(error);
            }}
        }}
    </script>
</body>
</html>
"""
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
        content=f"""
<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"utf-8\" />
    <title>{escape(title, quote=True)}</title>
    <style>
        body {{ font-family: sans-serif; margin: 2rem auto; max-width: 860px; line-height: 1.5; }}
        textarea, pre {{ width: 100%; box-sizing: border-box; }}
        textarea {{ min-height: 12rem; }}
        pre {{ background: #f5f5f5; padding: 1rem; overflow-x: auto; }}
    </style>
</head>
<body>
    <h1>{escape(title, quote=True)}</h1>
    <p>This window can be closed. The opener page will receive the login result automatically.</p>
    <pre id=\"payload\"></pre>
    <script>
        const payload = {payload_json};
        document.getElementById('payload').textContent = JSON.stringify(payload, null, 2);
        if (window.opener) {{
            window.opener.postMessage(payload, window.location.origin);
        }}
    </script>
</body>
</html>
"""
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


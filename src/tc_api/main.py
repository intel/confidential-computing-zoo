from fastapi import FastAPI, HTTPException, BackgroundTasks, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from html import escape
from typing import Any, Optional
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
from .tlog_client import TrustedLogAPI
from .tlog.types import Entry
from .models import *
from .services import DockerService
from .kbs_service import KBSService
from .oidc_preflight import inspect_identity_token
from .sigstore_identity import MissingSigstoreIdentityTokenError, cache_sigstore_identity_token, resolve_sigstore_identity_token
from .config import (
    HOST, PORT, DEBUG, UPLOAD_DIR, BUILD_DIR, LOGS_DIR,
    DOCKER_REGISTRY, DOCKER_REPOSITORY, ENABLE_TDX, TRUCON_URL,
    INIT_DEFAULT_CHAIN_ON_STARTUP,
    TRANSPARENCY_SERVICE_CHAIN_ID,
    TRANSPARENCY_WORKLOAD_CHAIN_PREFIX,
)

# Setup logging
logging.basicConfig(level=logging.DEBUG)
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


def workload_transparency_chain_id(workload_id: str) -> str:
    return f"{TRANSPARENCY_WORKLOAD_CHAIN_PREFIX}{workload_id}"


def _normalize_local_oci_reference(image_ref: Optional[str]) -> Optional[str]:
    if not image_ref:
        return image_ref
    if image_ref.startswith("oci:"):
        return image_ref
    if ":" not in image_ref and os.path.isdir(image_ref):
        return f"oci:{image_ref}"
    return image_ref


def has_proxy_configuration() -> bool:
    proxy_keys = (
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
    )
    return any(os.environ.get(key) for key in proxy_keys)


def log_proxy_configuration(operation: str) -> None:
    if has_proxy_configuration():
        logger.info("%s using configured proxy environment", operation)
    else:
        logger.info("%s running without proxy environment", operation)


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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    from .tlog_client import TrustedLogAPI
    from .trucon.adapters.sigstore import SigstoreLogAdapter
    
    # tc_api is stateless for the commit path — RTMR extend is TruCon's job.
    # local_mr is no longer used here.
    app.state.trusted_log = TrustedLogAPI(
        local_mr=None,
        immutable_log=SigstoreLogAdapter(),
        trucon_url=TRUCON_URL,
    )

    # Optionally initialize the default chain (Event Log 0 baseline).
    if INIT_DEFAULT_CHAIN_ON_STARTUP:
        try:
            app.state.trusted_log.init_chain("default")
        except Exception as e:
            logger.warning("init-chain for 'default' failed (non-fatal): %s", e)
    else:
        logger.info("Skipping default chain initialization during startup")
    
    yield
    
    # Shutdown logic
    logger.info("TC API Service shutting down...")

# Initialize FastAPI app
app = FastAPI(
    title="TC API - Trusted Container Build and Publish Service",
    description="RESTful API for building, signing, encrypting and publishing Docker images",
    version="1.0.0",
    lifespan=lifespan
)

# Initialize services
docker_service = DockerService()
kbs_service = KBSService()

# Create necessary directories
for directory in [UPLOAD_DIR, BUILD_DIR, LOGS_DIR]:
    os.makedirs(directory, exist_ok=True)
    logger.debug(f"Created directory: {directory}")


@app.get("/api/sigstore/interactive-login", response_class=HTMLResponse)
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


@app.get("/api/sigstore/identity-token")
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


@app.get("/api/sigstore/login-status/{session_id}")
async def sigstore_login_status(session_id: str):
    return _get_sigstore_login_status(session_id)


@app.get("/api/sigstore/callback", response_class=HTMLResponse)
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


@app.post("/api/sigstore/identity-token")
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

@app.get("/")
async def root():
    """Health check endpoint"""
    logger.info("Health check request received")
    return {"message": "TC API Service is running", "timestamp": datetime.now()}

@app.post("/api/build-package", response_model=BuildPackageResponse)
async def build_package(http_request: Request, request: BuildPackageRequest, background_tasks: BackgroundTasks):
    """Build and package a container image"""
    try:
        logger.info(f"Build package request received for user: {request.user_id}")
        request.identity_token = _resolve_required_sigstore_identity_token("build", request.identity_token, request=http_request)
        
        # Generate build ID
        build_id = docker_service.generate_uuid(prefix="bld")
        logger.debug(f"Generated build ID: {build_id}")
        
        tlog = app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id
        tlog.add_entry(record_id, Entry(key="build_id", value=build_id))

        # Create build directory
        build_path = os.path.join(BUILD_DIR, build_id)
        os.makedirs(build_path, exist_ok=True)
        logger.debug(f"Created build directory: {build_path}")

        tlog.add_entry(record_id, Entry(key="build_path", value=build_path))

        # Save dockerfile content
        dockerfile_path = os.path.join(build_path, "Dockerfile")
        with open(dockerfile_path, "w") as f:
            f.write(request.dockerfile)
        logger.debug(f"Saved Dockerfile to: {dockerfile_path}")

        # Save app binary if provided
        if request.app_binary:
            binary_path = os.path.join(build_path, "app.bin")
            binary_bytes = base64.b64decode(request.app_binary)
            with open(binary_path, "wb") as f:
                f.write(binary_bytes)
            logger.debug(f"Saved app binary to: {binary_path}")
            binary_hash = hashlib.sha256(binary_bytes).hexdigest()
            tlog.add_entry(record_id, Entry(key="app_binary", value={"app_binary_path": binary_path, "app_binary_hash": binary_hash}))
        
        # Save config files if provided
        if request.configs:
            config_dir = os.path.join(build_path, "configs")
            os.makedirs(config_dir, exist_ok=True)
            for i, config in enumerate(request.configs):
                config_path = os.path.join(config_dir, f"config_{i}")
                with open(config_path, "wb") as f:
                    f.write(base64.b64decode(config))
            logger.debug(f"Saved {len(request.configs)} config files")
            config_hashes = [hashlib.sha256(base64.b64decode(c)).hexdigest() for c in request.configs]
            tlog.add_entry(record_id, Entry(key="config", value={"config_dir": config_dir,
                                 "config_count": len(request.configs),
                                 "config_hashes": config_hashes}))

        # Save data files if provided
        if request.data:
            data_dir = os.path.join(build_path, "data")
            os.makedirs(data_dir, exist_ok=True)
            for i, data in enumerate(request.data):
                data_path = os.path.join(data_dir, f"data_{i}")
                with open(data_path, "wb") as f:
                    f.write(base64.b64decode(data))
            logger.debug(f"Saved {len(request.data)} data files")
            data_hashes = [hashlib.sha256(base64.b64decode(d)).hexdigest() for d in request.data]
            tlog.add_entry(record_id, Entry(key="data", value={"data_dir": data_dir,
                                 "data_count": len(request.data),
                                 "data_hashes": data_hashes}))
        
        # Initialize build status
        docker_service.update_build_status(request.user_id, build_id, "submitted")
        logger.info(f"Build {build_id} status updated to: submitted")
        # Start background build process
        background_tasks.add_task(
            build_container_async, 
            request, 
            build_id,
            tlog,
            record_id
        )
        logger.info(f"Started background build task for build ID: {build_id}")
        
        # Return immediately with submitted status
        return BuildPackageResponse(
            build_id=build_id,
            status="submitted",
            estimated_time="120s",
            user_id=request.user_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Build package request failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start build: {str(e)}")

def build_container_async(request: BuildPackageRequest, build_id: str, tlog: TrustedLogAPI, record_id: str):
    """Function to build container in background with detailed status tracking"""
    tlog_id = None
    try:
        # Start with preparing status
        docker_service.update_build_status(request.user_id, build_id, "preparing", step="Initializing build process")
        logger.info(f"Starting build process for build ID: {build_id}")
        
        # Build the image
        image_name = f"{request.user_id}-{build_id}:latest"
        logger.debug(f"Building image: {image_name}")
        tlog.add_entry(record_id, Entry(key="image_name", value=image_name))
        docker_service.update_build_status(request.user_id, build_id, "building", step="Building container image")
        build_success = docker_service.build_image(request.dockerfile, build_id, request.user_id, tlog, record_id)
        
        if not build_success:
            logger.error(f"Docker build failed for build ID: {build_id}")
            docker_service.update_build_status(request.user_id, build_id, "failed", step="Container build failed")
            return

        # Generate keys if not provided
        decryption_key = None
        public_encryption_key = None
        private_encryption_key = None
        encryption_key_source = "generated"
        logger.debug(f"Checking for provided sign_key and cert for build ID: {build_id}")
        if not request.sign_key or not request.cert:
            docker_service.update_build_status(request.user_id, build_id, "preparing", step="Get signing and encryption keys")
            logger.info(f"Get keys for build ID: {build_id}")
            if ENABLE_TDX:
                # Get key from KBS when TDX mode is enabled.
                logger.info("Starting get key from KBS")
                attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
                if attestation_result != "trusted":
                    docker_service.update_build_status(
                        request.user_id,
                        build_id,
                        "failed",
                        error_message="Attestation failed: get key failed."
                    )
                    logger.debug("get key failed")
                    return
                encryption_key_source = "kbs"
            else:
                logger.info("ENABLE_TDX=false, skipping KBS attestation key retrieval")
            
            docker_service.update_build_status(request.user_id, build_id, "preparing", step="Generating signing and encryption keys")
            logger.info(f"Generating keys for build ID: {build_id}")
            sign_key, cert, priv_enc_key, pub_enc_key = docker_service.generate_key(build_id, tlog, record_id)
            
            if not sign_key or not cert or not priv_enc_key or not pub_enc_key:
                logger.error(f"Failed to generate keys for build ID: {build_id}")
                docker_service.update_build_status(
                    request.user_id,
                    build_id, 
                    "failed",
                    step="Key generation failed",
                    error_message="Failed to generate keys"
                )
                return
                
            request.sign_key = sign_key
            request.cert = cert
            private_encryption_key = priv_enc_key
            public_encryption_key = pub_enc_key
            if not decryption_key:
                decryption_key = {"opensslPub": pub_enc_key}
                encryption_key_source = "generated"
            logger.debug(f"Successfully generated keys for build ID: {build_id}")
            
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "preparing",
                step="Keys generated successfully",
                cert_url=f"/api/artifacts/{build_id}/{os.path.basename(cert)}"
            )

        # Generate SBOM and handle encryption
        try:
            # Generate SBOM
            docker_service.update_build_status(request.user_id, build_id, "generating_sbom", step="Generating SBOM")
            logger.info(f"Generating SBOM for image {image_name}")
            sbom_path = docker_service.generate_sbom(
                image_name,
                build_id,
                tlog,
                record_id
            )
            if not sbom_path:
                raise Exception("SBOM generation failed")
            logger.debug(f"Successfully generated SBOM at {sbom_path}")

            # Encrypt image if requested
            if request.encrypt:
                if not decryption_key:
                    logger.error(f"Encryption requested for build {build_id}, but no encryption key available.")
                    raise Exception("Encryption requested, but no encryption key available")

                docker_service.update_build_status(request.user_id, build_id, "encrypting", step="Encrypting container image")
                logger.info(
                    "Encrypting image %s with key source=%s path=%s",
                    image_name,
                    encryption_key_source,
                    decryption_key.get("opensslPub"),
                )
                encrypted_image_name = docker_service.encrypt_image(
                    image_name,
                    build_id,
                    decryption_key['opensslPub'],
                    tlog,
                    record_id
                )
                if not encrypted_image_name:
                    raise Exception("Image encryption failed")
                logger.debug(f"Successfully encrypted image {image_name}")
                image_name = encrypted_image_name
            else:
                logger.info(f"Exporting non-encrypted image {image_name} to OCI layout")
                exported_image_name = docker_service.export_image_to_oci(
                    image_name,
                    build_id,
                    tlog,
                    record_id,
                )
                if not exported_image_name:
                    raise Exception("Image export failed")
                logger.debug(f"Successfully exported image {image_name}")
                image_name = exported_image_name

        except Exception as e:
            logger.error(f"Image encryption or SBOM generation failed for build ID {build_id}: {str(e)}")
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "failed",
                step="SBOM/Encryption failed",
                error_message=f"Image encryption or SBOM generation failed: {str(e)}"
            )
            return

        # Commit to TruCon and save receipt
        logger.info("Committing build transparency log")
        log_proxy_configuration("Build transparency log")

        identity_token = request.identity_token
        tlog_id = None
        tlog_status, tlog_id = docker_service.commit_and_save_receipt("build", build_id, tlog, record_id, identity_token)
        if tlog_id is not None:
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", build_id)
        if tlog_status:
            logger.info("Save build transparency success.")
        else:
            logger.info("Save build transparency failed.")
            docker_service.update_build_status(
                request.user_id,
                build_id,
                "failed",
                step="Transparency log commit failed",
                image_id=image_name,
                image_url=image_name,
                sbom_url=sbom_path,
                cert_url=f"/api/artifacts/{build_id}/cosign.crt",
                transparencyLog_verify="failed",
                error_message="Build transparency log commit failed",
            )
            return

        # Verify chain state via TruCon
        logger.info("Verify chain state")
        verify_tlog_status = docker_service.verify_chain_state("build", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)

        if image_name.startswith("oci:"):
            published_image_id = image_name
            published_image_url = image_name
            published_sbom_url = sbom_path
        else:
            published_image_id = image_name
            published_image_url = image_name
            published_sbom_url = sbom_path

        # Update build status with success
        logger.info(f"Build completed successfully for build ID: {build_id}")
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "success",
            step="Build completed successfully",
            image_id=published_image_id,
            log_id=tlog_id,
            sbom_url=published_sbom_url,
            image_url=published_image_url,
            transparencyLog_verify=verify_tlog_status,
            cert_url=f"/api/artifacts/{build_id}/cosign.crt"
        )
        
    except Exception as e:
        logger.error(f"Build failed for build ID {build_id}: {str(e)}")
        docker_service.update_build_status(
            request.user_id,
            build_id,
            "failed",
            step="Unexpected error",
            log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
            error_message=str(e)
        )

@app.post("/api/publish-package", response_model=PublishPackageResponse)
async def publish_package(http_request: Request, request: PublishPackageRequest):
    """Publish image and SBOM to registry with key management and logging"""
    try:
        request.identity_token = _resolve_required_sigstore_identity_token("publish", request.identity_token, request=http_request)
        image_name = request.image_id.split("/")[-1].split(":")[0]
        registry_repo = f"{DOCKER_REPOSITORY}/{image_name}:latest-encrypted"

        tlog = app.state.trusted_log
        ctx = tlog.init_record(context={"chain_ref": TRANSPARENCY_SERVICE_CHAIN_ID})
        record_id = ctx.record_id

        # 1. Push image and SBOM to registry
        try:
            # Generate build ID
            publish_id = "pub-" + request.build_id.split("-")[-1]
            logger.debug(f"Generated build ID: {publish_id}")
            tlog.add_entry(record_id, Entry(key="publishID", value={"publishID": publish_id}))

            docker_service.update_publish_status(request.user_id, request.build_id, "pushing", publish_id, step="Pushing image to registry")
            logger.info(f"Pushing image {request.image_id} to registry")
            
            if request.image_id.startswith("oci:"):
                source_ref = request.image_id
            else:
                source_ref = f"docker-daemon:{request.image_id}"
            dest_ref = f"docker://{registry_repo}"

            log_proxy_configuration("Publish image push")

            push_success = docker_service.push_image(source_ref, dest_ref, tlog, record_id)
            if not push_success:
                raise Exception("Image push failed")
            logger.debug(f"Successfully pushed image to {dest_ref}")
            tlog.add_entry(record_id, Entry(key="log", value={
                "publish_source": source_ref,
                "publish_dest": dest_ref,
                "publishImage_status": push_success
                }))
            

        except Exception as e:
            logger.error(f"Image push failed for build ID {request.build_id}: {str(e)}")
            tlog.add_entry(record_id, Entry(key="publish_status", value={"publish_status": "failed",
                                "error": str(e)}))
            docker_service.update_publish_status(
                request.user_id,
                request.build_id,
                "failed",
                publish_id,
                step="Image push failed",
                error_message=f"Image push failed: {str(e)}"
            )
            raise HTTPException(status_code=400, detail=f"Image push failed: {str(e)}")
        
        # Push SBOM
        logger.info(f"Starting get key from KBS")
        attestation_result, decryption_key = docker_service.get_pubKey_from_KBS(tlog, record_id)
        if decryption_key:
        # if request.sign_key and request.cert:
            try:
                docker_service.update_publish_status(request.user_id, request.build_id, "signing", publish_id, step="Signing image and SBOM")
                # Sign image
                logger.info(f"Signing image {request.image_id}")
                sign_success = docker_service.sign_image(
                    request.image_id,
                    decryption_key['cosignKey'],
                    tlog,
            record_id
                )
                if not sign_success:
                    raise Exception("Image signing failed")
                logger.debug(f"Successfully signed image {request.image_id}")
                tlog.add_entry(record_id, Entry(key="publish_sbom", value={"publish_sbom": sign_success}))

                # Create SBOM attestation
                logger.info(f"Creating SBOM attestation for build ID {request.build_id}")
                sbom_attestation_success = docker_service.create_sbom_attestation(
                    request.image_id,
                    request.sbom_url,
                    decryption_key['cosignKey'],
                    tlog,
            record_id
                )
                tlog.add_entry(record_id, Entry(key="verify_sbom_status", value={"verify_sbom_status": sbom_attestation_success}))
                if not sbom_attestation_success:
                    tlog.add_entry(record_id, Entry(key="verify_sbom_status", value={"verify_sbom_status": sbom_attestation_success}))
                    raise Exception("SBOM attestation failed")
                logger.debug(f"Successfully created SBOM attestation for build ID {request.build_id}")
                
            except Exception as e:
                logger.error(f"Image signing or SBOM attestation failed for build ID {request.build_id}: {str(e)}")
                tlog.add_entry({"error": f"{e}"})
                docker_service.update_publish_status(
                    request.user_id,
                    request.build_id,
                    "failed",
                    publish_id,
                    step="Signing failed",
                    #image_id=request.image_id,
                    #sbom_url=request.sbom_url,
                    #image_url=request.image_url,
                    error_message=f"Image signing or SBOM attestation failed: {str(e)}"
                )
                raise HTTPException(status_code=500, detail=f"Image signing or SBOM attestation failed: {str(e)}")

        identity_token = request.identity_token
        tlog_id = None

		# Sign and submit to transparency log
        tlog_status, tlog_id = docker_service.commit_and_save_receipt("publish", request.build_id, tlog, record_id, identity_token)
        docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "added", request.build_id)
        if tlog_status:
            logger.info(f"Save publish transparency success.")
        else:
            logger.info(f"Save publish transparency failed.")

		# Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_chain_state("publish", tlog, chain_id=TRANSPARENCY_SERVICE_CHAIN_ID)

        docker_service.update_publish_status(request.user_id, request.build_id, "success", publish_id,
                                             step="complete publish verify",
                                             transparencyLog_verify=verify_tlog_status,
                                             log_id=tlog_id,
                                             image_id=request.image_id.split('/')[-1],
                                             sbom_url=request.sbom_url,
                                             image_url=f"docker.io/{registry_repo}"
                                             )
        return PublishPackageResponse(
            build_id=request.build_id,
            publish_id=publish_id,
            status="success",
		    image_id=request.image_id.split('/')[-1],
            sbom_url=request.sbom_url,
		    image_url=f"docker.io/{registry_repo}",
		    user_id=request.user_id,
		    transparencyLog_verify=verify_tlog_status,
		    log_id=f"{tlog_id}" if tlog_id else f"uuid-{uuid.uuid4()}",
		    published_at=datetime.now()
		)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to publish package: {str(e)}"
        )


@app.get("/api/publish-result/{build_id}", response_model=PublishResult)
async def get_publish_result(build_id: str):
    """Get publish result by publish ID"""
    try:
        publish_result = docker_service.get_publish_status(build_id)
        
        if not publish_result:
            raise HTTPException(status_code=404, detail="Publish not found")
        
        return publish_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get publish result: {str(e)}")

@app.get("/api/build-result/{build_id}", response_model=BuildResult)
async def get_build_result(build_id: str):
    """Get build result by build ID"""
    try:
        build_result = docker_service.get_build_status(build_id)
        
        if not build_result:
            raise HTTPException(status_code=404, detail="Build not found")
        
        return build_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get build result: {str(e)}")

@app.get("/api/transparency-log/{log_id}", response_model=TransparencyResult)
async def get_transparencyLog(log_id: str):
    """Get transparency log result by build ID"""
    try:
        tlog_result = docker_service.get_transparencyLog_status(log_id)

        if not tlog_result:
            raise HTTPException(status_code=404, detail="Transparency log not found")

        return tlog_result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get transparency log result: {str(e)}")


@app.post("/api/deploy-launch", response_model=LaunchResponse)
async def deploy_launch(http_request: Request, request: LaunchRequest, background_tasks: BackgroundTasks):
    """Deploy and launch container on worker nodes"""
    try:
        request.identity_token = _resolve_required_sigstore_identity_token("launch", request.identity_token, request=http_request)
        tlog = app.state.trusted_log
        workload_id = docker_service.normalize_workload_id(request.user_id, request.image_id, request.metadata)
        transparency_chain_id = workload_transparency_chain_id(workload_id)
        ctx = tlog.init_record(context={"chain_ref": transparency_chain_id})
        record_id = ctx.record_id

        # Generate launch ID
        launch_id = docker_service.generate_uuid(prefix="launch")
        logger.info(f"CHECK launchID: {launch_id}")
        tlog.add_entry(record_id, Entry(key="launch_id", value={"launch_id": launch_id}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))

        # Create launch directory
        launch_path = os.path.join(BUILD_DIR, launch_id)
        tlog.add_entry(record_id, Entry(key="launch_path", value={"launch_path": launch_path}))
        os.makedirs(launch_path, exist_ok=True)

        # Save launch configuration
        config_path = os.path.join(launch_path, "launch_config.json")
        with open(config_path, "w") as f:
            json.dump(request.model_dump(), f, indent=2)
        
        # Initialize launch status
        docker_service.update_launch_status(
            user_id=request.user_id,
            launch_id=launch_id,
            status="initiated",
            created_at=datetime.now()
        )
        
        # Start background launch process
        background_tasks.add_task(
            launch_container_async,
            request,
            launch_id,
            workload_id,
            transparency_chain_id,
            launch_path,
            tlog,
            record_id
        )
        
        return LaunchResponse(
            launch_id=launch_id,
            status="initiated",
            user_id=request.user_id
        )
        
    except HTTPException:
        raise
    except Exception as e:
        # Clean up launch directory if creation failed
        if 'launch_path' in locals():
            shutil.rmtree(launch_path, ignore_errors=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to initiate launch: {str(e)}"
        )

async def launch_container_async(request: LaunchRequest, launch_id: str, workload_id: str, transparency_chain_id: str, launch_path: str, tlog: TrustedLogAPI, record_id: str):
    """Async function to launch container in background"""
    try:
        docker_service.update_launch_status(request.user_id, launch_id, "launching")
        
        # Create log file
        log_file = os.path.join(launch_path, "launch.log")
        with open(log_file, "w") as f:
            f.write(f"Launch started at {datetime.now().isoformat()}\n")
        tlog.add_entry(record_id, Entry(key="launch-log", value={"launch-log":log_file}))
        tlog.add_entry(record_id, Entry(key="workload_id", value=workload_id))
        image_digest = docker_service._resolve_image_digest(request.image_url or request.image_id)
        security_projection = docker_service._build_launch_security_projection(launch_id, workload_id)
        launch_config_digest = docker_service._json_sha384_digest({
            "request": request.model_dump(),
            "security_projection": security_projection,
        })
        tlog.add_entry(record_id, Entry(key="image_digest", value=image_digest))
        tlog.add_entry(record_id, Entry(key="launch_config_digest", value=launch_config_digest))
        tlog.add_entry(record_id, Entry(key="privileged", value=security_projection["privileged"]))
        tlog.add_entry(record_id, Entry(key="network_mode", value=security_projection["network_mode"]))
        tlog.add_entry(record_id, Entry(key="mounts", value=security_projection["mounts"]))
        tlog.add_entry(record_id, Entry(key="devices", value=security_projection["devices"]))
        tlog.add_entry(record_id, Entry(key="capabilities", value=security_projection["capabilities"]))
        tlog.add_entry(record_id, Entry(key="launch_env_keys", value=security_projection["launch_env_keys"]))
        tlog.add_entry(record_id, Entry(key="launch_env_digest", value=security_projection["launch_env_digest"]))

        # 3. Perform attestation and handle decryption
        attestation_result = "trusted"
        decryption_key = None
        if request.attestation_required:
            if ENABLE_TDX:
                # Verify attestation and get decryption key in TDX mode.
                logger.info("Attestation Verity and get keys")
                attestation_result, decryption_key = await docker_service.verify_attestation(
                    request.image_id,
                    request.user_id,
                    tlog,
            record_id
                )
                tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image":attestation_result}))
                tlog.add_entry(record_id, Entry(key="verify_keys", value={"verify_keys":decryption_key}))

                if attestation_result != "trusted":
                    docker_service.update_launch_status(
                        request.user_id,
                        launch_id,
                        "failed",
                        error_message=f"Attestation failed: {attestation_result}"
                    )
                    logger.debug("Attestation Verity and get keys failed")
                    tlog.add_entry(record_id, Entry(key="verify_image", value={"verify_image":attestation_result}))
                    return
            else:
                logger.info("ENABLE_TDX=false, skipping attestation flow")

        log_proxy_configuration("Launch image pull")

        # 1. Pull and verify image
        logger.info("Get encrypted image and decrypt")
        pull_success = docker_service.pull_image(
            tlog, record_id,
            image_url=request.image_url,
            target_dir=launch_path,
            openssl_key=decryption_key['opensslKey'] if decryption_key else None
        )
        if not pull_success:
            docker_service.update_launch_status(
                request.user_id,
                launch_id, 
                "failed",
                error_message="Image pull failed"
            )
            logger.debug("Get encrypted image and decrypt failed")
            tlog.add_entry(record_id, Entry(key="launch_result", value="failed"))
            return
            
        # 2. Verify SBOM if provided
        logger.info("Verify SBOM")
        if request.sbom_url:
            cosign_pubkey = None
            if decryption_key and isinstance(decryption_key, dict):
                cosign_pubkey = decryption_key.get("cosignPub")
            verify_image_ref = _normalize_local_oci_reference(request.image_url)

            if cosign_pubkey:
                sbom_valid = docker_service.verify_sbom(
                    verify_image_ref,
                    request.sbom_url,
                    tlog, record_id,
                    cosign_pubkey,
                )
            else:
                logger.info("Skipping SBOM verification because no cosign public key is available for launch")
                sbom_valid = True
            tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
            if not sbom_valid:
                docker_service.update_launch_status(
                    request.user_id,
                    launch_id,
                    "failed",
                    error_message="SBOM verification failed"
                )
                logger.debug("Verify SBOM failed")
                tlog.add_entry(record_id, Entry(key="sbom_verify", value={"sbom_verify": sbom_valid}))
                tlog.add_entry(record_id, Entry(key="launch_result", value="failed"))
                return
        
        # 4. Launch containers on worker nodes
        logger.info("Launch container")
        instance_ids = await docker_service.launch_containers(
            tlog, record_id,
            image_url=request.image_url,
            image_id=request.image_id,
            launch_pth=launch_path,
            workload_id=workload_id,
            launch_id=launch_id,
        )
        tlog.add_entry(record_id, Entry(key="launch_instance_ids", value={"launch_instance_ids": instance_ids}))
        if not instance_ids:
            docker_service.update_launch_status(
                request.user_id,
                launch_id,
                "failed",
                error_message="Container launch failed"
            )
            logger.debug("Launch container failed")
            tlog.add_entry(record_id, Entry(key="launch_result", value={"launch_result": "failed"}))
            return
            
        # 5. Create launch evidence
        evidences = {
            "launch_id": launch_id,
            "workload_id": workload_id,
            "image_id": request.image_id,
            "image_digest": image_digest,
            "launch_config_digest": launch_config_digest,
            "user_id": request.user_id,
            "timestamp": datetime.now().isoformat(),
            "attestation_result": attestation_result,
            "instance_ids": instance_ids
        }

        identity_token = request.identity_token
        log_id = None
        tlog_status, log_id = docker_service.commit_and_save_receipt("launch", launch_id, tlog, record_id, identity_token)
        docker_service.update_transparencylog_status(request.user_id, str(log_id), "added", launch_id)
        if tlog_status:
            logger.info(f"Save build transparency success.")
        else:
            logger.info(f"Save build transparency failed.")

        # Verify transparencyLog
        logger.info("Verify transparencyLog")
        verify_tlog_status = docker_service.verify_chain_state("launch", tlog, chain_id=transparency_chain_id)

        # Update launch status to success
        docker_service.update_launch_status(
            request.user_id,
            launch_id=launch_id,
            status="success",
            validation="passed",
            attestation=attestation_result,
            evidence=evidences,
            transparencyLog_verify=verify_tlog_status,
            log_id=f"{log_id}" if log_id else f"uuid-{uuid.uuid4()}",
            instance_ids=instance_ids
        )
        
    except Exception as e:
        docker_service.update_launch_status(
            request.user_id,
            launch_id,
            "failed",
            error_message=str(e)
        )
        # Log error to launch.log
        with open(os.path.join(launch_path, "launch.log"), "a") as f:
            f.write(f"Error: {str(e)}\n")

@app.get("/api/launch-result/{launch_id}", response_model=LaunchResult)
async def get_launch_result(launch_id: str):
    """Get launch result by launch ID"""
    try:
        launch_result = docker_service.get_launch_status(launch_id)
        
        if not launch_result:
            raise HTTPException(
                status_code=404,
                detail="Launch not found"
            )
        
        return launch_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get launch result: {str(e)}"
        )

@app.post("/api/get-summaryTransparencylog", response_model=SummaryTransparencyRespone)
async def get_summary_transparencylog(request: GetTransparencyRequest):
    """Get launch result by launch ID"""
    try:
        res = await docker_service.get_summaryTransparencylog(request.build_id, request.launch_id)

        if not res:
            raise HTTPException(
                status_code=404,
                detail="Launch not found"
            )

        return res

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get launch result: {str(e)}"
        )


@app.post("/api/create_lunks", response_model=CreateLunksRespone)
async def create_lunks(request: CreateLunksRequest):
    """create lunks"""
    try:
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id

        logger.info(f"Create Lunks block file for user: {request.user_id}")

        # create encrypted vfs
        tlog.add_entry(record_id, Entry(key="lunks", value={"lunks": "Start creating lunks blocks"}))
        mapdir,loopdevice = docker_service.create_lunks_block(request.user_id, tlog,request.passwd, request.vfs_size, request.vfs_path)
        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("create_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("create_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "creating lunks block", '')
            if tlog_status:
                logger.info(f"Save create_lunks transparency success.")
            else:
                logger.info(f"Save create_lunks transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("create_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

        del os.environ['http_proxy']
        del os.environ['https_proxy']

        docker_service.update_lunks_status(
            request.user_id,
            "create success",
            step="create_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )


        return CreateLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=mapdir,
            vfs_path=request.vfs_path,
            loop_device=loopdevice,
            vfs_size=request.vfs_size
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create lunks: {str(e)}"
        )

@app.post("/api/mount_lunks", response_model=MountLunksRespone)
async def create_lunks(request: MountLunksRequest):
    """mount lunks"""
    try:
        logger.info(f"Mount Lunks block file for user: {request.user_id}")
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id
        status = 'failed'
        # mount encrypted vfs
        mountPath = docker_service.mount_lunks_block(request.user_id, tlog, request.mapper_dir, request.passwd, request.mount_path,request.vfs_path,request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("mount_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("mount_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "mount_lunks block", '')
            if tlog_status:
                logger.info(f"Save build transparency success.")
            else:
                logger.info(f"Save build transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("mount_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

        del os.environ['http_proxy']
        del os.environ['https_proxy']

        if  verify_tlog_status == "success":
            status = "mount_lunks success"

        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="mount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )

        return MountLunksRespone(
            user_id=request.user_id,
            passwd=request.passwd,
            mapper_dir=request.mapper_dir,
            vfs_path=request.vfs_path,
            loop_device=request.loop_device,
            mount_path=request.mount_path
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mount lunks: {str(e)}"
        )

@app.post("/api/unmount_lunks", response_model=UnmountLunksRespone)
async def create_lunks(request: UnmountLunksRequest):
    """umount lunks"""
    try:
        logger.info(f"Umount Lunks block file for user: {request.user_id}")
        tlog = app.state.trusted_log
        ctx = tlog.init_record()
        record_id = ctx.record_id
        status = 'failed'
        # unmount encrypted vfs
        docker_service.unmount_lunks_block(request.user_id, tlog, request.mapper_dir, request.mount_path, request.loop_device)

        # Save transparencyLog
        logger.info("Save transparencyLog")
        #docker_service.update_transparencylog_status(request.user_id, 'LogID', "adding", build_id)
        os.environ['http_proxy'] = "http://child-prc.intel.com:913"
        os.environ['https_proxy'] = "http://child-prc.intel.com:913"

        if "http_proxy" in os.environ:
            print("Proxy is setted.")
        else:
            print("Proxy is unsetted.")

        identity_token = resolve_sigstore_identity_token("unmount_lunks", logger=logger, allow_interactive=True)
        tlog_id = None
        if identity_token:
            tlog_status, tlog_id = docker_service.commit_and_save_receipt("unmount_lunks", '', tlog, record_id, identity_token)
            docker_service.update_transparencylog_status(request.user_id, str(tlog_id), "unmount_lunks block", '')
            if tlog_status:
                logger.info(f"Save build transparency success.")
            else:
                logger.info(f"Save build transparency failed.")

            # Verify transparencyLog
            logger.info("Verify transparencyLog")
            verify_tlog_status = docker_service.verify_chain_state("unmount_lunks", tlog)
        else:
            verify_tlog_status = "skipped"

        del os.environ['http_proxy']
        del os.environ['https_proxy']
        if  verify_tlog_status == "success":
            status = "unmount_lunks success"
        docker_service.update_lunks_status(
            request.user_id,
            status,
            step="unmount_lunks completed successfully",
            log_id=tlog_id,
            transparencyLog_verify=verify_tlog_status
        )

        return UnmountLunksRespone(
            user_id=request.user_id,
            mapper_dir=request.mapper_dir,
            loop_device=request.loop_device,
            mount_path=request.mount_path
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unmount lunks: {str(e)}"
        )

@app.get("/api/lunks-result/{user_id}", response_model=LunksResult)
async def get_lunks_result(user_id: str):
    """Get lunks result by user ID"""
    try:
        lunks = docker_service.get_lunks_status(user_id)

        if not lunks:
            raise HTTPException(status_code=404, detail="User not found")

        return lunks

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get lunks result: {str(e)}")

def main() -> None:
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="debug")


if __name__ == "__main__":
    main()

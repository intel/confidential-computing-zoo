import argparse
import json
import os
import sys
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from typing import Any, Optional

import requests
from tc_api.cli.oidc_verification_code import acquire_sigstore_token_via_oob
from tc_api.sigstore_identity import cache_sigstore_identity_token


DEFAULT_BASE_URL = os.environ.get("TC_API_BASE_URL", "http://localhost:8000")
DEFAULT_BROWSER_BASE_URL = os.environ.get("TC_API_BROWSER_BASE_URL", "").strip()
DEFAULT_SIGSTORE_LOGIN_MODE = os.environ.get("TC_CLIENT_SIGSTORE_LOGIN", "auto").strip().lower() or "auto"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_SIGSTORE_WAIT_SECONDS = int(os.environ.get("TC_CLIENT_SIGSTORE_WAIT_SECONDS", "300"))
SIGSTORE_POLL_INTERVAL_SECONDS = 2
DEFAULT_DOCKTAP_SOCKET_PATH = os.environ.get("SOCK_BRIDGE_SOCKET", "/var/run/docktap/docker.sock")
DEFAULT_DOCKER_SOCKET_PATH = os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock")


class ClientError(RuntimeError):
    pass


@dataclass
class JsonResponse:
    status_code: int
    data: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class ApiClient:
    def __init__(self, base_url: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def request_json(self, method: str, path: str, payload: Optional[dict[str, Any]] = None) -> JsonResponse:
        url = f"{self.base_url}{path}"
        response = requests.request(
            method=method.upper(),
            url=url,
            json=payload,
            timeout=self.timeout_seconds,
            headers={"Accept": "application/json"},
        )
        try:
            data = response.json()
        except ValueError:
            data = {
                "error": "Server did not return JSON.",
                "status_code": response.status_code,
                "body": response.text,
            }
        return JsonResponse(status_code=response.status_code, data=data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Client CLI for the TC API control plane"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"TC API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument(
        "--browser-base-url",
        default=DEFAULT_BROWSER_BASE_URL,
        help="Browser-reachable base URL for interactive pages, e.g. http://server-ip:8000",
    )
    parser.add_argument(
        "--sigstore-login",
        choices=["auto", "server-session", "oob"],
        default=DEFAULT_SIGSTORE_LOGIN_MODE,
        help="Sigstore login mode: auto prefers browser-session but falls back to verification-code OOB when needed",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="HTTP timeout in seconds")
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Attempt to open the Sigstore login URL automatically when interactive login is required",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_payload_subcommand(name: str, help_text: str) -> argparse.ArgumentParser:
        subparser = subparsers.add_parser(name, help=help_text)
        payload_group = subparser.add_mutually_exclusive_group(required=True)
        payload_group.add_argument("--payload-json", help="Inline JSON payload")
        payload_group.add_argument("--payload-file", help="Path to a JSON payload file")
        payload_group.add_argument("--stdin", action="store_true", help="Read JSON payload from stdin")
        return subparser

    add_payload_subcommand("build", "POST /api/build-package")
    add_payload_subcommand("publish", "POST /api/publish-package")
    add_payload_subcommand("deploy", "POST /api/deploy-launch")

    build_result = subparsers.add_parser("build-result", help="GET /api/build-result/{build_id}")
    build_result.add_argument("build_id")

    publish_result = subparsers.add_parser("publish-result", help="GET /api/publish-result/{build_id}")
    publish_result.add_argument("build_id")

    launch_result = subparsers.add_parser("launch-result", help="GET /api/launch-result/{launch_id}")
    launch_result.add_argument("launch_id")

    tlog = subparsers.add_parser("transparency-log", help="GET /api/transparency-log/{log_id}")
    tlog.add_argument("log_id")

    token = subparsers.add_parser("sigstore-token", help="Acquire a Sigstore identity token for non-interactive producers such as Docktap")
    token.add_argument(
        "--format",
        dest="token_format",
        choices=["json", "export"],
        default="json",
        help="Output as JSON metadata or as a shell export snippet",
    )
    token.add_argument(
        "--env-var",
        default="DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
        help="Environment variable name to use when --format export is selected",
    )

    run_docktap = subparsers.add_parser(
        "run-docktap",
        help="Acquire a Sigstore identity token and immediately exec Docktap with it",
    )
    run_docktap.add_argument(
        "--socket-path",
        default=DEFAULT_DOCKTAP_SOCKET_PATH,
        help=f"Docktap listen socket path (default: {DEFAULT_DOCKTAP_SOCKET_PATH})",
    )
    run_docktap.add_argument(
        "--docker-socket-path",
        default=DEFAULT_DOCKER_SOCKET_PATH,
        help=f"Docker daemon socket path (default: {DEFAULT_DOCKER_SOCKET_PATH})",
    )
    run_docktap.add_argument(
        "--debug",
        action="store_true",
        help="Start Docktap with --debug enabled",
    )
    run_docktap.add_argument(
        "--env-var",
        default="DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
        help="Environment variable name used to pass the acquired identity token to Docktap",
    )

    return parser


def _load_json_payload(args: argparse.Namespace) -> dict[str, Any]:
    raw: str
    if getattr(args, "payload_json", None):
        raw = args.payload_json
    elif getattr(args, "payload_file", None):
        with open(args.payload_file, "r", encoding="utf-8") as handle:
            raw = handle.read()
    elif getattr(args, "stdin", False):
        raw = sys.stdin.read()
    else:
        raise ClientError("A payload source is required.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClientError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(payload, dict):
        raise ClientError("JSON payload must be an object.")
    return payload


def _print_json(data: Any) -> None:
    json.dump(data, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def _extract_sigstore_detail(data: Any) -> Optional[dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    detail = data.get("detail")
    if not isinstance(detail, dict):
        return None
    error_text = str(detail.get("error") or "")
    if "Sigstore identity token is required" not in error_text:
        return None
    return detail


def _maybe_open_browser(url: str, enabled: bool) -> None:
    if not enabled:
        return
    try:
        webbrowser.open(url)
    except Exception:
        return


def _path_from_url_or_path(value: str) -> str:
    parsed = requests.utils.urlparse(value)
    if not parsed.scheme and not parsed.netloc:
        return value
    path = parsed.path or "/"
    if parsed.query:
        return f"{path}?{parsed.query}"
    return path


def _absolute_url(base_url: str, value: str) -> str:
    raw_value = value.strip()
    if not raw_value:
        return raw_value
    parsed = urllib.parse.urlparse(raw_value)
    if parsed.scheme and parsed.netloc:
        return raw_value
    return urllib.parse.urljoin(f"{base_url.rstrip('/')}/", raw_value.lstrip("/"))


def _rewrite_browser_url(url: str, browser_base_url: str) -> str:
    raw_url = url.strip()
    if not raw_url or not browser_base_url.strip():
        return raw_url
    parsed_url = urllib.parse.urlparse(raw_url)
    parsed_base = urllib.parse.urlparse(browser_base_url.strip())
    if not parsed_url.scheme or not parsed_url.netloc:
        return raw_url
    if not parsed_base.scheme or not parsed_base.netloc:
        raise ClientError("--browser-base-url must be an absolute URL such as http://server-ip:8000")
    return urllib.parse.urlunparse(
        (
            parsed_base.scheme,
            parsed_base.netloc,
            parsed_url.path,
            parsed_url.params,
            parsed_url.query,
            parsed_url.fragment,
        )
    )


def _is_loopback_browser_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return host in {"localhost", "127.0.0.1", "::1"}


def _acquire_sigstore_token_oob(operation: str = "docktap") -> str:
    return acquire_sigstore_token_via_oob(operation=operation)


def _start_sigstore_identity_session(client: ApiClient, operation: str, flow: str) -> dict[str, Any]:
    query = urllib.parse.urlencode({"operation": operation, "flow": flow})
    response = client.request_json("GET", f"/api/sigstore/identity-token?{query}")
    if not response.ok:
        raise ClientError(json.dumps(response.data, ensure_ascii=False))
    if not isinstance(response.data, dict):
        raise ClientError("Server returned an invalid Sigstore login response.")
    return response.data


def _token_from_started_sigstore_session(
    client: ApiClient,
    login_payload: dict[str, Any],
    *,
    operation: str,
    open_browser: bool,
    browser_base_url: str,
    sigstore_login_mode: str,
) -> str:
    status = str(login_payload.get("status") or "").strip()
    if status == "token_ready":
        identity_token = str(login_payload.get("identity_token") or "").strip()
        if not identity_token:
            raise ClientError("Sigstore login completed but no identity_token was returned.")
        cache_sigstore_identity_token(identity_token)
        return identity_token

    if status != "browser_login_pending":
        raise ClientError(f"Unsupported Sigstore login status: {status or 'unknown'}")

    detail = {
        "after_login_open_url": _absolute_url(client.base_url, str(login_payload.get("interactive_login_url") or "")),
        "interactive_continue_url": _absolute_url(client.base_url, str(login_payload.get("interactive_login_url") or "")),
        "session_id": login_payload.get("session_id"),
        "login_status_url": _absolute_url(
            client.base_url,
            f"/api/sigstore/login-status/{login_payload.get('session_id')}",
        ),
    }
    return _complete_sigstore_login(
        client,
        detail,
        operation=operation,
        open_browser=open_browser,
        browser_base_url=browser_base_url,
        sigstore_login_mode=sigstore_login_mode,
    )


def _acquire_sigstore_token_for_cli(
    client: ApiClient,
    *,
    operation: str,
    open_browser: bool,
    browser_base_url: str,
    sigstore_login_mode: str,
) -> str:
    selected_mode = (sigstore_login_mode or "auto").strip().lower()
    if selected_mode == "oob":
        return _acquire_sigstore_token_oob(operation)

    requested_flow = "server-callback"
    if selected_mode == "auto" and not browser_base_url.strip() and not DEFAULT_BROWSER_BASE_URL:
        requested_flow = "copy-url"

    login_payload = _start_sigstore_identity_session(client, operation, requested_flow)
    token = _token_from_started_sigstore_session(
        client,
        login_payload,
        operation=operation,
        open_browser=open_browser,
        browser_base_url=browser_base_url,
        sigstore_login_mode=sigstore_login_mode,
    )
    if token:
        cache_sigstore_identity_token(token)
    return token


def _exec_docktap_with_identity_token(
    identity_token: str,
    *,
    socket_path: str,
    docker_socket_path: str,
    debug: bool,
    env_var: str,
) -> None:
    env = os.environ.copy()
    env[env_var] = identity_token

    argv = [sys.executable, "-m", "docktap.main", "--socket-path", socket_path, "--docker-socket-path", docker_socket_path]
    if debug:
        argv.append("--debug")

    os.execvpe(sys.executable, argv, env)


def _select_sigstore_login_mode(
    requested_mode: str,
    continue_url: str,
    browser_base_url: str,
) -> str:
    mode = (requested_mode or "auto").strip().lower()
    if mode in {"server-session", "oob"}:
        return mode
    if not continue_url:
        return "oob"
    if browser_base_url.strip():
        return "server-session"
    if _is_loopback_browser_url(continue_url):
        return "oob"
    return "server-session"


def _complete_sigstore_login(
    client: ApiClient,
    detail: dict[str, Any],
    operation: str,
    open_browser: bool,
    browser_base_url: str,
    sigstore_login_mode: str,
) -> str:
    continue_url = str(detail.get("after_login_open_url") or detail.get("interactive_continue_url") or "").strip()
    session_id = str(detail.get("session_id") or "").strip()
    status_url = str(detail.get("login_status_url") or f"/api/sigstore/login-status/{session_id}").strip()

    selected_mode = _select_sigstore_login_mode(sigstore_login_mode, continue_url, browser_base_url)
    if selected_mode == "oob":
        return _acquire_sigstore_token_oob(operation)

    if not continue_url or not session_id or not status_url:
        raise ClientError("Server did not return enough Sigstore login guidance to continue.")

    browser_continue_url = _rewrite_browser_url(continue_url, browser_base_url)

    print("Sigstore login required.", file=sys.stderr)
    print(f"Open this browser page and finish login there:\n  {browser_continue_url}", file=sys.stderr)
    if _is_loopback_browser_url(browser_continue_url):
        print(
            "This browser URL points at localhost. If your browser runs on another machine, rerun with --browser-base-url http://<server-ip>:8000.",
            file=sys.stderr,
        )
    print("Waiting for the server-side login session to complete...", file=sys.stderr)
    _maybe_open_browser(browser_continue_url, open_browser)

    deadline = time.monotonic() + DEFAULT_SIGSTORE_WAIT_SECONDS
    status_path = _path_from_url_or_path(status_url)
    while time.monotonic() < deadline:
        status_response = client.request_json("GET", status_path)
        if status_response.ok:
            status_payload = status_response.data if isinstance(status_response.data, dict) else {}
            if status_payload.get("status") == "token_ready":
                identity_token = str(status_payload.get("identity_token") or "").strip()
                if not identity_token:
                    raise ClientError("Sigstore login completed but no identity_token was returned.")
                return identity_token
        elif status_response.status_code != 404:
            raise ClientError(f"Sigstore login polling failed: {json.dumps(status_response.data, ensure_ascii=False)}")
        time.sleep(SIGSTORE_POLL_INTERVAL_SECONDS)

    raise ClientError(
        f"Timed out waiting for Sigstore login to finish for {operation}. Keep the browser page open and retry the command once login completes."
    )


def _request_with_sigstore_retry(
    client: ApiClient,
    method: str,
    path: str,
    payload: Optional[dict[str, Any]],
    sigstore_operation: Optional[str],
    open_browser: bool,
    browser_base_url: str,
    sigstore_login_mode: str,
) -> Any:
    response = client.request_json(method, path, payload)
    if response.ok:
        return response.data

    detail = _extract_sigstore_detail(response.data)
    if detail is None or sigstore_operation is None:
        raise ClientError(json.dumps(response.data, ensure_ascii=False))

    retry_payload = dict(payload or {})
    retry_payload["identity_token"] = _complete_sigstore_login(
        client,
        detail,
        operation=sigstore_operation,
        open_browser=open_browser,
        browser_base_url=browser_base_url,
        sigstore_login_mode=sigstore_login_mode,
    )
    retry_response = client.request_json(method, path, retry_payload)
    if not retry_response.ok:
        raise ClientError(json.dumps(retry_response.data, ensure_ascii=False))
    return retry_response.data


def _run_command(args: argparse.Namespace) -> Any:
    client = ApiClient(args.base_url, timeout_seconds=args.timeout)

    if args.command == "sigstore-token":
        identity_token = _acquire_sigstore_token_for_cli(
            client,
            operation="docktap",
            open_browser=args.open_browser,
            browser_base_url=args.browser_base_url,
            sigstore_login_mode=args.sigstore_login,
        )
        if args.token_format == "export":
            return f"export {args.env_var}={json.dumps(identity_token)}"
        return {"identity_token": identity_token}

    if args.command == "run-docktap":
        identity_token = _acquire_sigstore_token_for_cli(
            client,
            operation="docktap",
            open_browser=args.open_browser,
            browser_base_url=args.browser_base_url,
            sigstore_login_mode=args.sigstore_login,
        )
        _exec_docktap_with_identity_token(
            identity_token,
            socket_path=args.socket_path,
            docker_socket_path=args.docker_socket_path,
            debug=args.debug,
            env_var=args.env_var,
        )
        return None

    if args.command == "build":
        payload = _load_json_payload(args)
        return _request_with_sigstore_retry(client, "POST", "/api/build-package", payload, "build", args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "publish":
        payload = _load_json_payload(args)
        return _request_with_sigstore_retry(client, "POST", "/api/publish-package", payload, "publish", args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "deploy":
        payload = _load_json_payload(args)
        return _request_with_sigstore_retry(client, "POST", "/api/deploy-launch", payload, "launch", args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "build-result":
        return _request_with_sigstore_retry(client, "GET", f"/api/build-result/{args.build_id}", None, None, args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "publish-result":
        return _request_with_sigstore_retry(client, "GET", f"/api/publish-result/{args.build_id}", None, None, args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "launch-result":
        return _request_with_sigstore_retry(client, "GET", f"/api/launch-result/{args.launch_id}", None, None, args.open_browser, args.browser_base_url, args.sigstore_login)
    if args.command == "transparency-log":
        return _request_with_sigstore_retry(client, "GET", f"/api/transparency-log/{args.log_id}", None, None, args.open_browser, args.browser_base_url, args.sigstore_login)
    raise ClientError(f"Unsupported command: {args.command}")


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run_command(args)
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if isinstance(result, str):
        print(result)
        return 0
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
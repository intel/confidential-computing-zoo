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
 
import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from urllib import error, request


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TIMEOUT = 30
DEFAULT_BUILD_TIMEOUT = 900
DEFAULT_LAUNCH_TIMEOUT = 600
DEFAULT_POLL_INTERVAL = 5
DEFAULT_DOCKERFILE = """FROM alpine:3.20
RUN mkdir -p /opt/tcapi
COPY app.bin /opt/tcapi/app.bin
CMD [\"sh\", \"-c\", \"echo TDVM smoke test container started && sleep 300\"]
"""

REQUIRED_COMMANDS = ("docker", "cosign", "syft", "skopeo", "curl")
REQUIRED_TDX_PATHS = (
    Path("/dev/tdx_guest"),
    Path("/etc/tdx-attest.conf"),
)
OPTIONAL_TDX_PATHS = (
    Path("/etc/sgx_default_qcnl.conf"),
    Path("/var/run/docker.sock"),
)
REPO_ROOT = Path(__file__).resolve().parent
REAL_QUOTE_CHECK_SCRIPT = REPO_ROOT / "tests" / "check_real_tdx_quote.py"
SRC_ROOT = REPO_ROOT / "src"
DEFAULT_TRUCON_UDS_PATH = "/var/run/trucon/trucon.sock"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from tc_api.identity.sigstore_baseline import build_baseline_sigstore_bundle
from tc_api.identity.sigstore_identity import resolve_sigstore_identity_token
from tc_api.transparency.commit_client import TrustedLogAPI
from tc_api.trucon.adapters.ccel import read_ccel_eventlog_used_binary
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from tc_api.trucon.internal_transport import request_json, resolve_trucon_url


class SmokeTestError(RuntimeError):
    pass


class SimpleSession:
    def __init__(self):
        self.headers = {"Content-Type": "application/json"}

    def request(
        self,
        method: str,
        url: str,
        timeout: int,
        json_body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        data = None
        headers = dict(self.headers)
        if extra_headers:
            headers.update(extra_headers)
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")

        req = request.Request(url=url, data=data, headers=headers, method=method.upper())

        try:
            with request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                status = response.status
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise SmokeTestError(
                f"{method.upper()} {url} failed with status {exc.code}: {body.strip()}"
            ) from exc
        except error.URLError as exc:
            raise SmokeTestError(f"{method.upper()} {url} request failed: {exc}") from exc

        if status >= 400:
            raise SmokeTestError(f"{method.upper()} {url} failed with status {status}: {body.strip()}")

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise SmokeTestError(f"{method.upper()} {url} returned non-JSON response: {body.strip()}") from exc


def print_step(message: str) -> None:
    print(f"\n[tdvm-smoke] {message}")


def print_json(title: str, payload: Dict[str, Any]) -> None:
    print(f"[tdvm-smoke] {title}: {json.dumps(payload, ensure_ascii=True, indent=2, default=str)}")


def encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def load_text_file(path: Optional[str], fallback: str) -> str:
    if not path:
        return fallback
    return Path(path).read_text(encoding="utf-8")


def load_optional_text_file(path: Optional[str]) -> Optional[str]:
    if not path:
        return None
    return Path(path).read_text(encoding="utf-8")


def session_request(
    session: SimpleSession,
    method: str,
    url: str,
    action: str,
    timeout: int,
    **kwargs: Any,
) -> Dict[str, Any]:
    json_body = kwargs.get("json")
    extra_headers = kwargs.get("headers")
    try:
        return session.request(method=method, url=url, timeout=timeout, json_body=json_body, extra_headers=extra_headers)
    except SmokeTestError as exc:
        raise SmokeTestError(f"{action}: {exc}") from exc


def poll_status(
    session: SimpleSession,
    url: str,
    action: str,
    success_status: str,
    timeout_seconds: int,
    poll_interval: int,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: Dict[str, Any] = {}

    while time.monotonic() < deadline:
        latest = session_request(session, "GET", url, action, DEFAULT_TIMEOUT, headers=headers)
        status = latest.get("status")
        step = latest.get("current_step") or latest.get("validation") or latest.get("error_message")
        print(f"[tdvm-smoke] {action} status={status} detail={step}")

        if status == success_status:
            return latest
        if status == "failed":
            raise SmokeTestError(f"{action} failed: {json.dumps(latest, ensure_ascii=True, default=str)}")

        time.sleep(poll_interval)

    raise SmokeTestError(f"{action} timed out after {timeout_seconds}s: {json.dumps(latest, ensure_ascii=True, default=str)}")


def run_preflight(args: argparse.Namespace) -> None:
    print_step("Running TD VM preflight checks")

    missing_commands = [command for command in REQUIRED_COMMANDS if shutil.which(command) is None]
    if missing_commands:
        raise SmokeTestError(f"Missing required commands in TD VM: {', '.join(missing_commands)}")

    missing_required_paths = [str(path) for path in REQUIRED_TDX_PATHS if not path.exists()]
    if missing_required_paths and not args.allow_missing_tdx:
        raise SmokeTestError(
            "Missing required TDX paths: "
            + ", ".join(missing_required_paths)
            + ". Use --allow-missing-tdx only if you want to bypass this gate."
        )

    missing_optional_paths = [str(path) for path in OPTIONAL_TDX_PATHS if not path.exists()]
    if missing_optional_paths:
        print(f"[tdvm-smoke] Warning: optional paths missing: {', '.join(missing_optional_paths)}")

    if args.sign_key_file and not Path(args.sign_key_file).exists():
        raise SmokeTestError(f"sign key file not found: {args.sign_key_file}")
    if args.cert_file and not Path(args.cert_file).exists():
        raise SmokeTestError(f"certificate file not found: {args.cert_file}")

    if args.kbs_url:
        try:
            with request.urlopen(args.kbs_url, timeout=10) as response:
                print(f"[tdvm-smoke] KBS probe status={response.status} url={args.kbs_url}")
        except error.URLError as exc:
            raise SmokeTestError(f"KBS probe failed for {args.kbs_url}: {exc}") from exc


def run_health_check(session: SimpleSession, base_url: str) -> Dict[str, Any]:
    print_step("Checking TC API health")
    payload = session_request(session, "GET", f"{base_url}/", "health check", DEFAULT_TIMEOUT)
    print_json("Health response", payload)
    return payload


def run_quote_check(args: argparse.Namespace) -> Dict[str, Any]:
    print_step("Running real TDX quote check")

    if not REAL_QUOTE_CHECK_SCRIPT.exists():
        raise SmokeTestError(f"Quote check script missing: {REAL_QUOTE_CHECK_SCRIPT}")

    cmd = [sys.executable, str(REAL_QUOTE_CHECK_SCRIPT), "--repo-root", str(REPO_ROOT)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=args.quote_check_timeout)

    if result.stderr.strip():
        print(f"[tdvm-smoke] quote check stderr: {result.stderr.strip()}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise SmokeTestError(f"Quote check returned non-JSON output: {result.stdout.strip()}") from exc

    print_json("Quote check", payload)
    if result.returncode != 0:
        raise SmokeTestError("Repository TDX quote adapter check failed")
    return payload


def _entry_value(predicate_entries: list[Dict[str, Any]], key: str) -> Optional[str]:
    for entry in predicate_entries:
        if isinstance(entry, dict) and entry.get("key") == key:
            value = entry.get("value")
            return value if isinstance(value, str) else None
    return None


def _trucon_request(
    method: str,
    path: str,
    timeout: int,
    json_body: Optional[Dict[str, Any]] = None,
    trucon_url: Optional[str] = None,
    uds_path: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        return request_json(
            method,
            path,
            json_body=json_body,
            caller_service="tc_api",
            timeout=timeout,
            trucon_url=trucon_url,
            uds_path=uds_path,
        )
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp is not None else ""
        raise SmokeTestError(
            f"{method.upper()} {path} via TruCon failed with status {exc.code}: {body.strip()}"
        ) from exc
    except error.URLError as exc:
        raise SmokeTestError(f"{method.upper()} {path} via TruCon failed: {exc}") from exc


def run_baseline_chain_smoke(args: argparse.Namespace) -> Dict[str, Any]:
    print_step("Running Event Log 0 baseline smoke against real TD VM CCEL material")

    identity_token = resolve_sigstore_identity_token("tdvm_smoke_baseline", allow_interactive=False)
    if not identity_token:
        raise SmokeTestError(
            "No reusable Sigstore identity token is available for baseline smoke. "
            "Run tc_api.identity.oidc_preflight --fetch --force-oob or set TC_API_REAL_REKOR_IDENTITY_TOKEN."
        )

    local_ccel_bytes = read_ccel_eventlog_used_binary()
    if not local_ccel_bytes:
        raise SmokeTestError("Unable to read non-empty CCEL event log bytes from the current TD VM")

    local_ccel_b64 = encode_bytes(local_ccel_bytes)
    chain_id = f"{args.user_id_prefix}-baseline-{uuid.uuid4().hex[:8]}"
    trucon_url = resolve_trucon_url(args.trucon_url)
    trucon_uds_path = args.trucon_uds_path or (
        DEFAULT_TRUCON_UDS_PATH if Path(DEFAULT_TRUCON_UDS_PATH).exists() else None
    )

    baseline = _trucon_request(
        "GET",
        f"/init-chain/{chain_id}/baseline",
        DEFAULT_TIMEOUT,
        trucon_url=trucon_url,
        uds_path=trucon_uds_path,
    )
    print_json(
        "Baseline response",
        {
            "chain_id": chain_id,
            "rtmr_value": baseline.get("rtmr_value"),
            "ccel_digest": baseline.get("ccel_digest"),
            "ccel_eventlog_b64_chars": len(baseline.get("ccel_eventlog_b64") or ""),
            "ccel_eventlog_matches_local": baseline.get("ccel_eventlog_b64") == local_ccel_b64,
        },
    )

    baseline_ccel_b64 = baseline.get("ccel_eventlog_b64")
    if baseline_ccel_b64 != local_ccel_b64:
        raise SmokeTestError("Baseline endpoint returned CCEL event log bytes that do not match local TD VM CCEL material")

    reserve = _trucon_request(
        "POST",
        "/commit-intents/reserve",
        DEFAULT_TIMEOUT,
        json_body={
            "chain_id": chain_id,
            "idempotency_key": f"tdvm-smoke-init-{chain_id}",
            "is_baseline": True,
        },
        trucon_url=trucon_url,
        uds_path=trucon_uds_path,
    )

    signed_bundle, pub_key_pem, event_digest = build_baseline_sigstore_bundle(
        chain_id=chain_id,
        rtmr_value=baseline.get("rtmr_value"),
        ccel_digest=baseline.get("ccel_digest"),
        ccel_eventlog_b64=baseline_ccel_b64,
        identity_token_str=identity_token,
        rekor_url=args.rekor_url,
        sequence_num=reserve.get("sequence_num", 1),
        prev_event_digest=reserve.get("prev_event_digest"),
        prev_lookup_hash=reserve.get("prev_lookup_hash"),
    )

    init_result = _trucon_request(
        "POST",
        "/init-chain",
        DEFAULT_TIMEOUT,
        json_body={
            "chain_id": chain_id,
            "init_token": baseline["init_token"],
            "intent_token": reserve.get("intent_token"),
            "signed_bundle": signed_bundle,
            "pub_key": pub_key_pem,
        },
        trucon_url=trucon_url,
        uds_path=trucon_uds_path,
    )
    print_json("Baseline init submission", init_result)

    deadline = time.monotonic() + args.baseline_timeout
    state: Dict[str, Any] = {}
    verify_chain: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        state = _trucon_request(
            "GET",
            "/chain-state",
            DEFAULT_TIMEOUT,
            trucon_url=trucon_url,
            uds_path=trucon_uds_path,
        )
        verify_chain = _trucon_request(
            "GET",
            "/verify-chain",
            DEFAULT_TIMEOUT,
            trucon_url=trucon_url,
            uds_path=trucon_uds_path,
        )
        print(
            "[tdvm-smoke] baseline chain status="
            f"head_log_id={state.get('head_log_id')} confirmed={verify_chain.get('rekor_confirmed')} "
            f"pending={verify_chain.get('rekor_pending')} valid={verify_chain.get('valid')}"
        )
        if state.get("head_log_id") and verify_chain.get("rekor_confirmed") == 1 and verify_chain.get("rekor_pending") == 0:
            break
        time.sleep(args.poll_interval)
    else:
        raise SmokeTestError(
            "Baseline chain did not reach confirmed immutable state before timeout: "
            + json.dumps({"state": state, "verify_chain": verify_chain}, ensure_ascii=True, default=str)
        )

    adapter = SigstoreLogAdapter(rekor_url=args.rekor_url) if args.rekor_url else SigstoreLogAdapter()
    tlog = TrustedLogAPI(immutable_log=adapter, trucon_url=trucon_url)
    verify_result = tlog.verify_record(
        state["head_log_id"],
        policy={"chain_id": chain_id, "expected_entry_count": 1},
    )
    if not verify_result.success:
        raise SmokeTestError(
            "Immutable replay verification for baseline smoke failed: "
            + json.dumps(verify_result.errors, ensure_ascii=True, default=str)
        )

    entry = verify_result.details["entries"][0]
    predicate_entries = entry.get("predicate_entries") or []
    replay_ccel_b64 = _entry_value(predicate_entries, "ccel_eventlog_b64")
    if replay_ccel_b64 != local_ccel_b64:
        raise SmokeTestError("Immutable replay Event Log 0 payload did not preserve the local TD VM CCEL event log bytes")

    try:
        replay_ccel_bytes = base64.b64decode(replay_ccel_b64, validate=True) if replay_ccel_b64 else b""
        replay_ccel_decodable = True
    except Exception:
        replay_ccel_bytes = b""
        replay_ccel_decodable = False

    result = {
        "chain_id": chain_id,
        "trucon_url": trucon_url,
        "trucon_uds_path": trucon_uds_path,
        "record_id": init_result.get("record_id"),
        "head_log_id": state.get("head_log_id"),
        "sequence_num": state.get("sequence_num"),
        "event_id": entry.get("event_id"),
        "event_type": entry.get("event_type"),
        "event_digest": entry.get("digest") or event_digest,
        "verify_success": verify_result.success,
        "baseline_rtmr": _entry_value(predicate_entries, "baseline_rtmr"),
        "ccel_digest": _entry_value(predicate_entries, "ccel_digest"),
        "ccel_eventlog_b64_chars": len(replay_ccel_b64 or ""),
        "ccel_eventlog_decodable": replay_ccel_decodable,
        "ccel_eventlog_bytes": len(replay_ccel_bytes),
        "ccel_eventlog_matches_local": replay_ccel_bytes == local_ccel_bytes,
        "local_ccel_bytes": len(local_ccel_bytes),
    }
    print_json("Baseline immutable replay audit", result)
    return result


def run_build(
    session: SimpleSession,
    base_url: str,
    args: argparse.Namespace,
    user_id: str,
    identity_token: Optional[str] = None,
) -> Dict[str, Any]:
    print_step("Submitting build-package request")

    dockerfile = load_text_file(args.dockerfile, DEFAULT_DOCKERFILE)
    sign_key = load_optional_text_file(args.sign_key_file)
    cert = load_optional_text_file(args.cert_file)

    build_payload: Dict[str, Any] = {
        "dockerfile": dockerfile,
        "app_binary": encode_bytes(f"tdvm-smoke-{uuid.uuid4().hex}".encode("utf-8")),
        "configs": [encode_bytes(b"mode=tdvm-smoke\n")],
        "data": [encode_bytes(json.dumps({"ts": int(time.time())}).encode("utf-8"))],
        "encrypt": not args.no_encrypt,
        "user_id": user_id,
    }
    if sign_key:
        build_payload["sign_key"] = sign_key
    if cert:
        build_payload["cert"] = cert
    if identity_token:
        build_payload["identity_token"] = identity_token

    result_headers = {"Authorization": f"Bearer {identity_token}"} if identity_token else None

    response = session_request(
        session,
        "POST",
        f"{base_url}/api/build-package",
        "build-package submit",
        DEFAULT_TIMEOUT,
        json=build_payload,
    )
    print_json("Build submission", response)

    build_id = response.get("build_id")
    if not build_id:
        raise SmokeTestError("build-package response missing build_id")

    result = poll_status(
        session,
        f"{base_url}/api/build-result/{build_id}",
        f"build-result {build_id}",
        success_status="success",
        timeout_seconds=args.build_timeout,
        poll_interval=args.poll_interval,
        headers=result_headers,
    )

    if not result.get("image_id"):
        raise SmokeTestError(f"build {build_id} succeeded but image_id is missing")
    if not result.get("sbom_url"):
        raise SmokeTestError(f"build {build_id} succeeded but sbom_url is missing")

    print_json("Build result", result)
    return result


def has_registry_configuration() -> bool:
    repository = os.environ.get("DOCKER_REPOSITORY", "").strip()
    if not repository:
        return False
    if "#" in repository:
        return False
    return True


def run_publish(
    session: SimpleSession,
    base_url: str,
    args: argparse.Namespace,
    build_result: Dict[str, Any],
    user_id: str,
    identity_token: Optional[str] = None,
) -> Dict[str, Any]:
    print_step("Submitting publish-package request")

    payload = {
        "build_id": build_result["build_id"],
        "image_id": build_result["image_id"],
        "user_id": user_id,
        "sbom_url": build_result["sbom_url"],
        "log_evidence": True,
        "identity_token": identity_token,
        "metadata": {
            "smoke_test": "tdvm",
            "requested_at": int(time.time()),
        },
    }

    response = session_request(
        session,
        "POST",
        f"{base_url}/api/publish-package",
        "publish-package",
        args.publish_timeout,
        json=payload,
    )
    print_json("Publish response", response)

    publish_result = session_request(
        session,
        "GET",
        f"{base_url}/api/publish-result/{build_result['build_id']}",
        "publish-result",
        DEFAULT_TIMEOUT,
        headers={"Authorization": f"Bearer {identity_token}"} if identity_token else None,
    )
    print_json("Publish result", publish_result)

    if publish_result.get("status") != "success":
        raise SmokeTestError(f"publish-result did not reach success: {json.dumps(publish_result, ensure_ascii=True, default=str)}")

    return response


def run_deploy(
    session: SimpleSession,
    base_url: str,
    args: argparse.Namespace,
    build_result: Dict[str, Any],
    publish_result: Dict[str, Any],
    user_id: str,
    identity_token: Optional[str] = None,
) -> Dict[str, Any]:
    print_step("Submitting deploy-launch request")

    deploy_payload = {
        "image_id": publish_result.get("image_id") or Path(str(build_result["image_id"])).name,
        "user_id": user_id,
        "image_url": publish_result.get("image_url"),
        "sbom_url": build_result.get("sbom_url"),
        "attestation_required": not args.no_attestation,
        "identity_token": identity_token,
        "metadata": {
            "smoke_test": "tdvm",
            "source_build_id": build_result["build_id"],
        },
    }

    if not deploy_payload["image_url"]:
        raise SmokeTestError("deploy-launch requires image_url from publish response")

    response = session_request(
        session,
        "POST",
        f"{base_url}/api/deploy-launch",
        "deploy-launch submit",
        DEFAULT_TIMEOUT,
        json=deploy_payload,
    )
    print_json("Deploy submission", response)

    launch_id = response.get("launch_id")
    if not launch_id:
        raise SmokeTestError("deploy-launch response missing launch_id")

    result = poll_status(
        session,
        f"{base_url}/api/launch-result/{launch_id}",
        f"launch-result {launch_id}",
        success_status="success",
        timeout_seconds=args.launch_timeout,
        poll_interval=args.poll_interval,
        headers={"Authorization": f"Bearer {identity_token}"} if identity_token else None,
    )
    print_json("Launch result", result)
    return result


def write_summary(path: Optional[str], summary: Dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.write_text(json.dumps(summary, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
    print(f"[tdvm-smoke] Summary written to {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke test runner for TC API inside a real TD VM")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="TC API base URL")
    parser.add_argument("--dockerfile", help="Path to a Dockerfile used for build-package")
    parser.add_argument("--sign-key-file", help="Optional signing key file to include in build-package")
    parser.add_argument("--cert-file", help="Optional certificate file to include in build-package")
    parser.add_argument("--user-id-prefix", default="tdvm-smoke", help="Prefix used to generate unique user_id")
    parser.add_argument("--build-timeout", type=int, default=DEFAULT_BUILD_TIMEOUT, help="Seconds to wait for build success")
    parser.add_argument("--publish-timeout", type=int, default=300, help="Request timeout for publish-package")
    parser.add_argument("--launch-timeout", type=int, default=DEFAULT_LAUNCH_TIMEOUT, help="Seconds to wait for launch success")
    parser.add_argument("--poll-interval", type=int, default=DEFAULT_POLL_INTERVAL, help="Polling interval in seconds")
    parser.add_argument("--summary-file", help="Optional path to write smoke test summary JSON")
    parser.add_argument("--kbs-url", help="Optional KBS probe URL used by preflight")
    parser.add_argument("--quote-check-timeout", type=int, default=120, help="Seconds to wait for the repository TDX quote check")
    parser.add_argument("--baseline-timeout", type=int, default=180, help="Seconds to wait for baseline immutable confirmation")
    parser.add_argument("--trucon-url", help="Override TruCon base URL for baseline smoke")
    parser.add_argument("--trucon-uds-path", help="Override TruCon UDS path for baseline smoke")
    parser.add_argument("--rekor-url", help="Override Rekor base URL for baseline smoke verification")
    parser.add_argument("--skip-preflight", action="store_true", help="Skip local TD VM preflight checks")
    parser.add_argument("--skip-quote-check", action="store_true", help="Skip the repository real TDX quote acquisition check")
    parser.add_argument("--skip-baseline-smoke", action="store_true", help="Skip Event Log 0 baseline immutable smoke check")
    parser.add_argument("--skip-publish", action="store_true", help="Run only health and build")
    parser.add_argument("--skip-deploy", action="store_true", help="Run health, build and publish only")
    parser.add_argument("--no-attestation", action="store_true", help="Disable attestation in deploy-launch request")
    parser.add_argument("--no-encrypt", action="store_true", help="Disable encryption in build-package request")
    parser.add_argument("--allow-missing-tdx", action="store_true", help="Do not fail preflight when required TDX paths are missing")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = SimpleSession()
    base_url = args.base_url.rstrip("/")
    user_id = f"{args.user_id_prefix}-{uuid.uuid4().hex[:8]}"

    summary: Dict[str, Any] = {
        "base_url": base_url,
        "user_id": user_id,
        "preflight": None,
        "quote_check": None,
        "health": None,
        "baseline": None,
        "build": None,
        "publish": None,
        "launch": None,
    }

    try:
        if not args.skip_preflight:
            run_preflight(args)
            summary["preflight"] = "passed"
        else:
            summary["preflight"] = "skipped"

        if not args.skip_quote_check:
            summary["quote_check"] = run_quote_check(args)
        else:
            summary["quote_check"] = "skipped"

        summary["health"] = run_health_check(session, base_url)

        stage_identity_token: Optional[str] = None
        if not args.skip_publish:
            stage_identity_token = resolve_sigstore_identity_token(
                "tdvm_smoke_build_publish",
                allow_interactive=False,
                min_ttl_seconds=0,
            )
            if not stage_identity_token:
                raise SmokeTestError(
                    "No reusable Sigstore identity token is available for build/publish transparency logging. "
                    "Run tc_api.identity.oidc_preflight --fetch --force-oob immediately before the smoke test."
                )

        build_result = run_build(session, base_url, args, user_id, identity_token=stage_identity_token)
        summary["build"] = build_result

        if args.skip_publish:
            if not args.skip_baseline_smoke:
                summary["baseline"] = run_baseline_chain_smoke(args)
            else:
                summary["baseline"] = "skipped"
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through build stage")
            return 0

        if not has_registry_configuration():
            summary["publish"] = "skipped: DOCKER_REPOSITORY is not configured for registry push"
            summary["launch"] = "skipped: publish stage was skipped"
            if not args.skip_baseline_smoke:
                summary["baseline"] = run_baseline_chain_smoke(args)
            else:
                summary["baseline"] = "skipped"
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through build stage; publish/deploy skipped because DOCKER_REPOSITORY is not configured")
            return 0

        publish_result = run_publish(
            session,
            base_url,
            args,
            build_result,
            user_id,
            identity_token=stage_identity_token,
        )
        summary["publish"] = publish_result

        if not args.skip_baseline_smoke:
            summary["baseline"] = run_baseline_chain_smoke(args)
        else:
            summary["baseline"] = "skipped"

        if args.skip_deploy:
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through publish stage")
            return 0

        deploy_identity_token = resolve_sigstore_identity_token(
            "tdvm_smoke_deploy",
            allow_interactive=False,
            min_ttl_seconds=0,
        )
        if not deploy_identity_token:
            raise SmokeTestError(
                "No reusable Sigstore identity token is available for deploy transparency logging. "
                "Run tc_api.identity.oidc_preflight --fetch --force-oob immediately before the smoke test."
            )

        launch_result = run_deploy(
            session,
            base_url,
            args,
            build_result,
            publish_result,
            user_id,
            identity_token=deploy_identity_token,
        )
        summary["launch"] = launch_result
        write_summary(args.summary_file, summary)
        print_step("TD VM smoke test completed successfully")
        return 0
    except SmokeTestError as exc:
        summary["error"] = str(exc)
        write_summary(args.summary_file, summary)
        print(f"[tdvm-smoke] FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
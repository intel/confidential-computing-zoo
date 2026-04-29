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
    ) -> Dict[str, Any]:
        data = None
        headers = dict(self.headers)
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
    try:
        return session.request(method=method, url=url, timeout=timeout, json_body=json_body)
    except SmokeTestError as exc:
        raise SmokeTestError(f"{action}: {exc}") from exc


def poll_status(
    session: SimpleSession,
    url: str,
    action: str,
    success_status: str,
    timeout_seconds: int,
    poll_interval: int,
) -> Dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: Dict[str, Any] = {}

    while time.monotonic() < deadline:
        latest = session_request(session, "GET", url, action, DEFAULT_TIMEOUT)
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


def run_build(
    session: SimpleSession,
    base_url: str,
    args: argparse.Namespace,
    user_id: str,
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
) -> Dict[str, Any]:
    print_step("Submitting publish-package request")

    payload = {
        "build_id": build_result["build_id"],
        "image_id": build_result["image_id"],
        "user_id": user_id,
        "sbom_url": build_result["sbom_url"],
        "log_evidence": True,
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
) -> Dict[str, Any]:
    print_step("Submitting deploy-launch request")

    deploy_payload = {
        "image_id": publish_result.get("image_id") or Path(str(build_result["image_id"])).name,
        "user_id": user_id,
        "image_url": publish_result.get("image_url"),
        "sbom_url": build_result.get("sbom_url"),
        "attestation_required": not args.no_attestation,
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
    parser.add_argument("--skip-preflight", action="store_true", help="Skip local TD VM preflight checks")
    parser.add_argument("--skip-quote-check", action="store_true", help="Skip the repository real TDX quote acquisition check")
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
        build_result = run_build(session, base_url, args, user_id)
        summary["build"] = build_result

        if args.skip_publish:
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through build stage")
            return 0

        if not has_registry_configuration():
            summary["publish"] = "skipped: DOCKER_REPOSITORY is not configured for registry push"
            summary["launch"] = "skipped: publish stage was skipped"
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through build stage; publish/deploy skipped because DOCKER_REPOSITORY is not configured")
            return 0

        publish_result = run_publish(session, base_url, args, build_result, user_id)
        summary["publish"] = publish_result

        if args.skip_deploy:
            write_summary(args.summary_file, summary)
            print_step("Smoke test completed through publish stage")
            return 0

        launch_result = run_deploy(session, base_url, args, build_result, publish_result, user_id)
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
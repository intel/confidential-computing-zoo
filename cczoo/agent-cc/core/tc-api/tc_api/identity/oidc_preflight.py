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
import getpass
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import jwt
from sigstore.oidc import IdentityToken, Issuer
import sigstore.oidc as sigstore_oidc
from .sigstore_identity import cache_sigstore_identity_token


DEFAULT_TOKEN_ENV = "TC_API_REAL_REKOR_IDENTITY_TOKEN"
DEFAULT_EXPECTED_IDENTITY_ENV = "TC_API_REAL_REKOR_SIGNER_IDENTITY"
DEFAULT_REAL_REKOR_TEST_PATH = "tests/test_real_rekor_integration.py"
DEFAULT_REAL_REKOR_OCI_MULTI_CHAIN_TEST = (
    "tests/test_real_rekor_integration.py::test_public_rekor_real_oci_multi_chain_verify_smoke"
)


def _format_timestamp(epoch: Any) -> Optional[str]:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except Exception:
        return str(epoch)


def _load_token(args: argparse.Namespace) -> str:
    if args.prompt_token:
        token = getpass.getpass("OIDC token: ").strip()
    elif args.stdin:
        token = os.sys.stdin.read().strip()
    else:
        token = os.getenv(args.env_var, "").strip()
    if not token:
        raise ValueError(
            f"No token supplied. Set {args.env_var}, pass --stdin, or use --prompt-token for interactive entry."
        )
    cache_sigstore_identity_token(token)
    return token


def _load_expected_identity(args: argparse.Namespace) -> Optional[str]:
    if args.expected_identity:
        return args.expected_identity
    if args.prompt_expected_identity:
        value = input("Expected signer identity (optional): ").strip()
        return value or None
    return None


def _browser_fallback_commands(url: str) -> list[list[str]]:
    if sys.platform == "darwin":
        return [["open", url]]
    if os.name == "nt":
        return [["cmd", "/c", "start", "", url]]
    return [["xdg-open", url]]


def _open_login_browser(url: str) -> bool:
    print(f"Opening browser for login: {url}", file=sys.stderr)
    original_open = getattr(sigstore_oidc.webbrowser, "_oidc_preflight_original_open", sigstore_oidc.webbrowser.open)
    try:
        if original_open(url):
            return True
    except Exception as exc:
        print(f"Automatic browser open failed: {exc}", file=sys.stderr)

    for command in _browser_fallback_commands(url):
        executable = command[0]
        if executable != "cmd" and shutil.which(executable) is None:
            continue
        try:
            subprocess.Popen(command)
            return True
        except Exception:
            continue

    print(f"If the browser did not open automatically, visit:\n\n\t{url}", file=sys.stderr)
    return False


def _fetch_token(args: argparse.Namespace) -> str:
    issuer = Issuer.production()
    original_open = sigstore_oidc.webbrowser.open
    sigstore_oidc.webbrowser._oidc_preflight_original_open = original_open
    if not args.force_oob:
        sigstore_oidc.webbrowser.open = lambda url, *_args, **_kwargs: _open_login_browser(url)
    try:
        token = issuer.identity_token(
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            force_oob=args.force_oob,
        )
    finally:
        sigstore_oidc.webbrowser.open = original_open
        if hasattr(sigstore_oidc.webbrowser, "_oidc_preflight_original_open"):
            delattr(sigstore_oidc.webbrowser, "_oidc_preflight_original_open")
    if isinstance(token, IdentityToken):
        raw_token = str(token)
    else:
        raw_token = str(token).strip()
    cache_sigstore_identity_token(raw_token)
    return raw_token


def _utc_now_epoch() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def inspect_identity_token(raw_token: str, expected_identity: Optional[str] = None) -> Dict[str, Any]:
    try:
        claims = jwt.decode(
            raw_token,
            options={
                "verify_signature": False,
                "verify_aud": False,
                "verify_iat": False,
                "verify_exp": False,
            },
        )
    except Exception as exc:
        return {
            "valid_for_sigstore": False,
            "errors": [f"Identity token is malformed or missing claims: {exc}"],
            "warnings": [],
            "issuer": None,
            "audience": None,
            "subject": None,
            "email": None,
            "issued_at": None,
            "not_before": None,
            "expires_at": None,
            "sigstore_default_audience": getattr(sigstore_oidc, "_DEFAULT_AUDIENCE", "sigstore"),
            "known_issuer_identity_claim": None,
            "derived_identity": None,
            "federated_issuer": None,
            "expected_identity": expected_identity,
            "identity_matches_expected": None,
        }

    result: Dict[str, Any] = {
        "valid_for_sigstore": False,
        "errors": [],
        "warnings": [],
        "issuer": claims.get("iss"),
        "audience": claims.get("aud"),
        "subject": claims.get("sub"),
        "email": claims.get("email"),
        "issued_at": _format_timestamp(claims.get("iat")),
        "not_before": _format_timestamp(claims.get("nbf")),
        "expires_at": _format_timestamp(claims.get("exp")),
        "sigstore_default_audience": getattr(sigstore_oidc, "_DEFAULT_AUDIENCE", "sigstore"),
        "known_issuer_identity_claim": None,
        "derived_identity": None,
        "federated_issuer": None,
        "expected_identity": expected_identity,
        "identity_matches_expected": None,
    }

    issuer = claims.get("iss")
    known_map = getattr(sigstore_oidc, "_KNOWN_OIDC_ISSUERS", {})
    identity_claim = known_map.get(issuer)
    result["known_issuer_identity_claim"] = identity_claim or "sub"

    try:
        identity_token = IdentityToken(raw_token)
        result["valid_for_sigstore"] = True
        result["derived_identity"] = identity_token.identity
        result["federated_issuer"] = identity_token.federated_issuer
    except Exception as exc:
        result["errors"].append(str(exc))

    audience = claims.get("aud")
    default_audience = result["sigstore_default_audience"]
    audience_values = audience if isinstance(audience, list) else [audience]
    if default_audience not in audience_values:
        result["errors"].append(
            f"Token audience does not include '{default_audience}'. Current aud={audience!r}"
        )

    if issuer not in known_map:
        result["warnings"].append(
            "Issuer is not one of sigstore-python's known issuers. Sigstore will fall back to the 'sub' claim as identity."
        )

    now_epoch = _utc_now_epoch()
    issued_at = claims.get("iat")
    not_before = claims.get("nbf")
    expires_at = claims.get("exp")

    if issued_at is None:
        result["errors"].append("Token is missing the 'iat' claim.")
    if expires_at is None:
        result["errors"].append("Token is missing the 'exp' claim.")

    try:
        if not_before is not None and int(not_before) > now_epoch:
            result["errors"].append("Token is not valid yet (nbf is in the future).")
    except Exception:
        result["errors"].append(f"Token has a non-integer 'nbf' claim: {not_before!r}")

    try:
        if expires_at is not None:
            expires_epoch = int(expires_at)
            result["expires_in_seconds"] = expires_epoch - now_epoch
            if expires_epoch <= now_epoch:
                result["errors"].append("Token has already expired.")
            elif expires_epoch - now_epoch <= 20:
                result["warnings"].append(
                    "Token expires in 20 seconds or less. Acquire it immediately before running the smoke test."
                )
    except Exception:
        result["errors"].append(f"Token has a non-integer 'exp' claim: {expires_at!r}")

    if expected_identity is not None and result["derived_identity"] is not None:
        result["identity_matches_expected"] = result["derived_identity"] == expected_identity
        if not result["identity_matches_expected"]:
            result["errors"].append(
                f"Derived signer identity {result['derived_identity']!r} does not match expected {expected_identity!r}"
            )

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire and preflight-check an OIDC token for Sigstore/Fulcio compatibility without printing the raw token by default"
    )
    parser.add_argument(
        "--env-var",
        default=DEFAULT_TOKEN_ENV,
        help=f"Environment variable containing the OIDC token (default: {DEFAULT_TOKEN_ENV})",
    )
    parser.add_argument(
        "--expected-identity",
        default=os.getenv(DEFAULT_EXPECTED_IDENTITY_ENV),
        help=(
            "Expected signer identity to compare against. Defaults to the value of "
            f"{DEFAULT_EXPECTED_IDENTITY_ENV} when present."
        ),
    )
    parser.add_argument(
        "--prompt-expected-identity",
        action="store_true",
        help="Prompt for the expected signer identity instead of only reading --expected-identity or the environment",
    )
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read the token from stdin instead of an environment variable",
    )
    parser.add_argument(
        "--prompt-token",
        action="store_true",
        help="Prompt securely for the OIDC token instead of reading it from stdin or an environment variable",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Fetch a fresh token via sigstore-python's OIDC flow instead of reading one from stdin or the environment",
    )
    parser.add_argument(
        "--oidc-client-id",
        default="sigstore",
        help="OIDC client ID to use when --fetch is enabled (default: sigstore)",
    )
    parser.add_argument(
        "--oidc-client-secret",
        default="",
        help="OIDC client secret to use when --fetch is enabled",
    )
    parser.add_argument(
        "--force-oob",
        action="store_true",
        help="Force the sigstore OIDC flow to use the out-of-band path when --fetch is enabled",
    )
    parser.add_argument(
        "--run-real-rekor-smoke",
        action="store_true",
        help="After a successful preflight, run the opt-in public Rekor smoke test with the freshly loaded token",
    )
    parser.add_argument(
        "--run-real-rekor-oci-multi-chain-smoke",
        action="store_true",
        help="After a successful preflight, run the opt-in real Rekor + real OCI mirror + real verify multi-chain smoke test",
    )
    parser.add_argument(
        "--pytest-args",
        nargs=argparse.REMAINDER,
        help="Additional arguments to pass to pytest when --run-real-rekor-smoke is enabled",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _load_or_fetch_token(args: argparse.Namespace) -> str:
    if args.fetch:
        return _fetch_token(args)
    return _load_token(args)


def _build_smoke_command(args: argparse.Namespace) -> list[str]:
    target = DEFAULT_REAL_REKOR_TEST_PATH
    if args.run_real_rekor_oci_multi_chain_smoke:
        target = DEFAULT_REAL_REKOR_OCI_MULTI_CHAIN_TEST
    command = [sys.executable, "-m", "pytest", target]
    if args.pytest_args:
        command.extend(args.pytest_args)
    else:
        command.append("-q")
    return command


def _run_real_rekor_smoke(args: argparse.Namespace, token: str) -> int:
    command = _build_smoke_command(args)
    env = os.environ.copy()
    env[args.env_var] = token
    env["TC_API_RUN_REAL_REKOR_TESTS"] = "1"
    if args.run_real_rekor_oci_multi_chain_smoke:
        env["TC_API_RUN_REAL_OCI_MIRROR_TESTS"] = "1"
        print("Running real Rekor + real OCI mirror + real verify multi-chain smoke test with a freshly acquired token...")
    else:
        print("Running public Rekor smoke test with a freshly acquired token...")
    return subprocess.run(command, env=env, check=False).returncode


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    smoke_exit_code = None

    try:
        token = _load_or_fetch_token(args)
        expected_identity = _load_expected_identity(args)
        result = inspect_identity_token(token, expected_identity=expected_identity)
        if args.fetch:
            result["token_source"] = "sigstore-oidc-fetch"
        elif args.prompt_token:
            result["token_source"] = "interactive-prompt"
        elif args.stdin:
            result["token_source"] = "stdin"
        else:
            result["token_source"] = args.env_var
        if args.expected_identity:
            result["expected_identity_source"] = "cli-or-env"
        elif args.prompt_expected_identity:
            result["expected_identity_source"] = "interactive-prompt"

        if (args.run_real_rekor_smoke or args.run_real_rekor_oci_multi_chain_smoke) and result.get("valid_for_sigstore") and not result.get("errors"):
            smoke_exit_code = _run_real_rekor_smoke(args, token)
            result["smoke_test_exit_code"] = smoke_exit_code
    except Exception as exc:
        result = {
            "valid_for_sigstore": False,
            "errors": [str(exc)],
            "warnings": [],
        }

    if args.json_output:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"valid_for_sigstore: {result.get('valid_for_sigstore')}")
        for key in [
            "issuer",
            "federated_issuer",
            "audience",
            "subject",
            "email",
            "derived_identity",
            "expected_identity",
            "identity_matches_expected",
            "token_source",
            "issued_at",
            "not_before",
            "expires_at",
            "expires_in_seconds",
            "known_issuer_identity_claim",
            "smoke_test_exit_code",
        ]:
            if key in result:
                print(f"{key}: {result.get(key)}")
        if result.get("warnings"):
            print("warnings:")
            for item in result["warnings"]:
                print(f"- {item}")
        if result.get("errors"):
            print("errors:")
            for item in result["errors"]:
                print(f"- {item}")

    if not result.get("valid_for_sigstore") or result.get("errors"):
        return 1
    if smoke_exit_code is not None:
        return smoke_exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
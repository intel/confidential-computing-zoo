import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import jwt
from sigstore.oidc import IdentityToken
import sigstore.oidc as sigstore_oidc


DEFAULT_TOKEN_ENV = "TC_API_REAL_REKOR_IDENTITY_TOKEN"
DEFAULT_EXPECTED_IDENTITY_ENV = "TC_API_REAL_REKOR_SIGNER_IDENTITY"


def _format_timestamp(epoch: Any) -> Optional[str]:
    if epoch is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
    except Exception:
        return str(epoch)


def _load_token(args: argparse.Namespace) -> str:
    if args.stdin:
        token = os.sys.stdin.read().strip()
    else:
        token = os.getenv(args.env_var, "").strip()
    if not token:
        raise ValueError(
            f"No token supplied. Set {args.env_var} or pass --stdin to read the token from stdin."
        )
    return token


def inspect_identity_token(raw_token: str, expected_identity: Optional[str] = None) -> Dict[str, Any]:
    claims = jwt.decode(
        raw_token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_iat": False,
            "verify_exp": False,
        },
    )

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

    if expected_identity is not None and result["derived_identity"] is not None:
        result["identity_matches_expected"] = result["derived_identity"] == expected_identity
        if not result["identity_matches_expected"]:
            result["errors"].append(
                f"Derived signer identity {result['derived_identity']!r} does not match expected {expected_identity!r}"
            )

    return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preflight-check an OIDC token for Sigstore/Fulcio compatibility without printing the raw token"
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
        "--stdin",
        action="store_true",
        help="Read the token from stdin instead of an environment variable",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        token = _load_token(args)
        result = inspect_identity_token(token, expected_identity=args.expected_identity)
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
            "issued_at",
            "not_before",
            "expires_at",
            "known_issuer_identity_claim",
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

    return 0 if result.get("valid_for_sigstore") and not result.get("errors") else 1


if __name__ == "__main__":
    raise SystemExit(main())
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
import json
import os
import sys
from typing import Optional

from sigstore.oidc import IdentityToken, Issuer

from tc_api.identity.sigstore_identity import cache_sigstore_identity_token


DEFAULT_CLIENT_ID = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_ID", "sigstore")
DEFAULT_CLIENT_SECRET = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_SECRET", "")


def acquire_sigstore_token_via_oob(
    *,
    operation: str = "sigstore",
    client_id: str = DEFAULT_CLIENT_ID,
    client_secret: str = DEFAULT_CLIENT_SECRET,
    cache_token: bool = True,
    stderr=None,
) -> str:
    stream = stderr or sys.stderr
    print(f"Using Sigstore verification-code flow for {operation}.", file=stream)
    print(
        "A public Sigstore login URL will be shown next. Open it in your browser, complete login, and paste the verification code back here.",
        file=stream,
    )
    print(
        "The verification code is short-lived, usually about 1 minute. Paste it immediately after the browser shows it.",
        file=stream,
    )

    issuer = Issuer.production()
    token = issuer.identity_token(
        client_id=client_id,
        client_secret=client_secret,
        force_oob=True,
    )
    token_str = str(token).strip() if isinstance(token, IdentityToken) else str(token).strip()
    if cache_token and token_str:
        cache_sigstore_identity_token(token_str)
    return token_str


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Acquire a Sigstore OIDC token via verification-code flow and cache it for tc_api workflows"
    )
    parser.add_argument(
        "--operation",
        default="sigstore",
        help="Operation label shown to the user, e.g. baseline or docktap",
    )
    parser.add_argument(
        "--format",
        choices=["json", "export", "raw", "none"],
        default="json",
        help="How to print the acquired token after it has been cached",
    )
    parser.add_argument(
        "--env-var",
        default="TC_API_REAL_REKOR_IDENTITY_TOKEN",
        help="Environment variable name used when --format export is selected",
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    token = acquire_sigstore_token_via_oob(operation=args.operation)
    if args.format == "none":
        print("Sigstore identity token acquired and cached.", file=sys.stderr)
        return 0
    if args.format == "raw":
        print(token)
        return 0
    if args.format == "export":
        print(f"export {args.env_var}={json.dumps(token)}")
        return 0

    json.dump({"identity_token": token}, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
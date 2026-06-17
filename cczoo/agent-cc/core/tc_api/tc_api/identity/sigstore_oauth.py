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

import base64
import hashlib
import os
import urllib.parse
from typing import Optional

from fastapi import HTTPException


SIGSTORE_OIDC_ISSUER_URL = os.environ.get("TC_API_SIGSTORE_OIDC_ISSUER", "https://oauth2.sigstore.dev/auth")
SIGSTORE_OIDC_CLIENT_ID = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_ID", "sigstore")
SIGSTORE_OIDC_CLIENT_SECRET = os.environ.get("TC_API_SIGSTORE_OIDC_CLIENT_SECRET", "")
SIGSTORE_OIDC_SESSION_TTL_SECONDS = max(60, int(os.environ.get("TC_API_SIGSTORE_OIDC_SESSION_TTL_SECONDS", "600")))
SIGSTORE_OOB_REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def sigstore_provider_callback_base_url() -> str:
    return urllib.parse.urljoin(SIGSTORE_OIDC_ISSUER_URL.rstrip("/") + "/", "callback")


def get_sigstore_issuer():
    from sigstore.oidc import Issuer

    production = getattr(Issuer, "production", None)
    if callable(production):
        return production()
    return Issuer(SIGSTORE_OIDC_ISSUER_URL)


def build_sigstore_pkce_pair() -> tuple[str, str]:
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("utf-8")
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode("utf-8")).digest()
    ).rstrip(b"=").decode("utf-8")
    return code_verifier, code_challenge


def normalize_sigstore_login_flow(flow: Optional[str]) -> str:
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
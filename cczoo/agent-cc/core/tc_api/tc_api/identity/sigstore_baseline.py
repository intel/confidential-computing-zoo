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

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Optional
from threading import Lock

from sigstore._internal.fulcio.client import FulcioClient
from sigstore._internal.rekor.client import RekorClient
from sigstore._internal.trust import TrustedRoot
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from sigstore.dsse import StatementBuilder, Subject
from sigstore.oidc import IdentityToken
from sigstore.sign import SigningContext
from ..config import OWNER_KEY_DIR
from .sigstore_identity import clear_sigstore_identity_token_cache, resolve_sigstore_identity_token_object
from tlog.digest import canonical_json as _canonical_json, compute_entry_digest as _compute_entry_digest, compute_event_digest as _compute_event_digest


_OWNER_KEY_LOCK = Lock()
_CHAIN_OWNER_PRIVATE_KEYS: dict[str, ec.EllipticCurvePrivateKey] = {}


def _owner_key_path(chain_id: str) -> str:
    digest = hashlib.sha256(chain_id.encode("utf-8")).hexdigest()
    return os.path.join(OWNER_KEY_DIR, f"{digest}.pem")


def _load_owner_private_key_from_disk(chain_id: str) -> Optional[ec.EllipticCurvePrivateKey]:
    key_path = _owner_key_path(chain_id)
    if not os.path.exists(key_path):
        return None

    with open(key_path, "rb") as key_file:
        key_bytes = key_file.read()
    private_key = serialization.load_pem_private_key(key_bytes, password=None)
    if not isinstance(private_key, ec.EllipticCurvePrivateKey):
        raise TypeError(f"Unexpected owner key type for chain '{chain_id}'")
    return private_key


def _store_owner_private_key_to_disk(chain_id: str, private_key: ec.EllipticCurvePrivateKey) -> None:
    os.makedirs(OWNER_KEY_DIR, exist_ok=True)
    try:
        os.chmod(OWNER_KEY_DIR, 0o700)
    except OSError:
        pass

    key_path = _owner_key_path(chain_id)
    pem_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with open(key_path, "wb") as key_file:
        key_file.write(pem_bytes)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass


def _get_or_create_chain_owner_private_key(chain_id: str) -> ec.EllipticCurvePrivateKey:
    with _OWNER_KEY_LOCK:
        private_key = _CHAIN_OWNER_PRIVATE_KEYS.get(chain_id)
        if private_key is not None:
            return private_key

        private_key = _load_owner_private_key_from_disk(chain_id)
        if private_key is None:
            private_key = ec.generate_private_key(ec.SECP384R1())
            _store_owner_private_key_to_disk(chain_id, private_key)

        _CHAIN_OWNER_PRIVATE_KEYS[chain_id] = private_key
        return private_key


def _resolve_identity_token(identity_token_str: Optional[str] = None, force_refresh: bool = False) -> IdentityToken:
    if identity_token_str:
        return IdentityToken(identity_token_str)

    token = resolve_sigstore_identity_token_object("baseline", allow_interactive=True, force_refresh=force_refresh)
    if token is None:
        raise RuntimeError(
            "No reusable Sigstore identity token is available for baseline signing. "
            "Set TC_API_REAL_REKOR_IDENTITY_TOKEN, pre-populate the token cache, "
            "or run from an interactive terminal so a fresh token can be acquired."
        )
    return token


def _sign_baseline_statement(signing_context: SigningContext, statement, identity_token_str: Optional[str]):
    identity_token = _resolve_identity_token(identity_token_str)
    try:
        with signing_context.signer(identity_token, cache=True) as signer:
            return signer.sign_dsse(statement)
    except Exception:
        if identity_token_str:
            raise
        clear_sigstore_identity_token_cache()
        refreshed_identity_token = _resolve_identity_token(force_refresh=True)
        with signing_context.signer(refreshed_identity_token, cache=True) as signer:
            return signer.sign_dsse(statement)


def generate_chain_owner_pub_key_pem(chain_id: str) -> str:
    private_key = _get_or_create_chain_owner_private_key(chain_id)

    pub_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return pub_key_pem


def get_chain_owner_private_key(chain_id: str) -> Optional[ec.EllipticCurvePrivateKey]:
    return _get_or_create_chain_owner_private_key(chain_id)


def sign_dsse_with_owner_key(
    statement_json: str,
    private_key: ec.EllipticCurvePrivateKey,
) -> dict:
    """Sign an In-Toto Statement as a DSSE envelope using the owner key.

    Uses ECDSA P-384 + SHA-256 (Rekor server verification constraint).
    Returns the DSSE envelope dict with payloadType, payload (base64), and
    signatures (list with one entry containing 'sig' in base64).
    """
    import base64

    payload_type = "application/vnd.in-toto+json"
    statement_bytes = statement_json.encode("utf-8")
    payload_b64 = base64.b64encode(statement_bytes).decode("utf-8")

    # DSSE Pre-Authentication Encoding (PAE)
    pae = (
        f"DSSEv1 {len(payload_type)} {payload_type} "
        f"{len(statement_bytes)} {statement_json}"
    ).encode("utf-8")

    signature_der = private_key.sign(pae, ec.ECDSA(hashes.SHA256()))
    signature_b64 = base64.b64encode(signature_der).decode("utf-8")

    return {
        "payloadType": payload_type,
        "payload": payload_b64,
        "signatures": [{"sig": signature_b64}],
    }


def build_signing_context(rekor_url: Optional[str] = None) -> SigningContext:
    if not rekor_url or rekor_url == "https://rekor.sigstore.dev":
        return SigningContext.production()

    return SigningContext(
        fulcio=FulcioClient.production(),
        rekor=RekorClient(rekor_url),
        trusted_root=TrustedRoot.production(),
    )


def build_baseline_sigstore_bundle(
    chain_id: str,
    rtmr_value: Optional[str],
    ccel_digest: Optional[str],
    ccel_eventlog_b64: Optional[str] = None,
    identity_token_str: Optional[str] = None,
    rekor_url: Optional[str] = None,
    sequence_num: int = 1,
    prev_event_digest: Optional[str] = None,
    prev_lookup_hash: Optional[str] = None,
) -> tuple[str, str, str]:
    pub_key_pem = generate_chain_owner_pub_key_pem(chain_id)
    event_id = f"evt-log0-{chain_id}"
    event_type = "chain.init"
    created_iso = datetime.now(timezone.utc).isoformat()
    entries = [
        {"key": "baseline_rtmr", "value": rtmr_value or "null"},
        {
            "key": "ccel_eventlog_b64" if ccel_eventlog_b64 is not None else "ccel_digest",
            "value": ccel_eventlog_b64 if ccel_eventlog_b64 is not None else (ccel_digest or "null"),
        },
        {"key": "pub_key", "value": pub_key_pem},
    ]
    entry_digests = [_compute_entry_digest(entry["key"], entry["value"]) for entry in entries]
    event_digest = _compute_event_digest(event_id, event_type, created_iso, entry_digests)
    predicate_payload = {
        "event_id": event_id,
        "event_type": event_type,
        "created": created_iso,
        "entries": entries,
        "entry_digests": entry_digests,
        "digest": event_digest,
        "chain_id": chain_id,
        "sequence_num": sequence_num,
        "prev_event_digest": prev_event_digest,
        "prev_lookup_hash": prev_lookup_hash,
    }
    statement = (
        StatementBuilder()
        .subjects(
            [
                Subject(
                    name=f"trusted-log-chain_{chain_id}",
                    digest={"sha384": event_digest.removeprefix("sha384:")},
                )
            ]
        )
        .predicate_type("https://trusted-log.dev/v1")
        .predicate(predicate_payload)
        .build()
    )

    signing_context = build_signing_context(rekor_url)
    bundle = _sign_baseline_statement(signing_context, statement, identity_token_str)

    return bundle.to_json(), pub_key_pem, event_digest
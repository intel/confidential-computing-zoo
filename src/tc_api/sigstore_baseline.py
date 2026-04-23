import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from threading import Lock

from sigstore._internal.fulcio.client import FulcioClient
from sigstore._internal.rekor.client import RekorClient
from sigstore._internal.trust import TrustedRoot
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from sigstore.dsse import StatementBuilder, Subject
from sigstore.oidc import IdentityToken, Issuer
from sigstore.sign import SigningContext


_OWNER_KEY_LOCK = Lock()
_CHAIN_OWNER_PRIVATE_KEYS: dict[str, ec.EllipticCurvePrivateKey] = {}


def _canonical_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


def _compute_entry_digest(key: str, value: Any) -> str:
    payload = _canonical_json({"key": key, "value": value})
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


def _compute_event_digest(event_id: str, event_type: str, created_iso: str, entry_digests: list[str]) -> str:
    payload = _canonical_json(
        {
            "created": created_iso,
            "entry_digests": entry_digests,
            "event_id": event_id,
            "event_type": event_type,
        }
    )
    return "sha384:" + hashlib.sha384(payload.encode("utf-8")).hexdigest()


def _resolve_identity_token(identity_token_str: Optional[str] = None) -> IdentityToken:
    if identity_token_str:
        return IdentityToken(identity_token_str)

    token = Issuer.production().identity_token()
    if isinstance(token, IdentityToken):
        return token
    return IdentityToken(str(token))


def generate_chain_owner_pub_key_pem(chain_id: str) -> str:
    with _OWNER_KEY_LOCK:
        private_key = _CHAIN_OWNER_PRIVATE_KEYS.get(chain_id)
        if private_key is None:
            private_key = ec.generate_private_key(ec.SECP384R1())
            _CHAIN_OWNER_PRIVATE_KEYS[chain_id] = private_key

    pub_key_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return pub_key_pem


def get_chain_owner_private_key(chain_id: str) -> Optional[ec.EllipticCurvePrivateKey]:
    with _OWNER_KEY_LOCK:
        private_key = _CHAIN_OWNER_PRIVATE_KEYS.get(chain_id)
        if private_key is None:
            private_key = ec.generate_private_key(ec.SECP384R1())
            _CHAIN_OWNER_PRIVATE_KEYS[chain_id] = private_key
        return private_key


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
        {"key": "ccel_digest", "value": ccel_digest or "null"},
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
    identity_token = _resolve_identity_token(identity_token_str)
    with signing_context.signer(identity_token, cache=True) as signer:
        bundle = signer.sign_dsse(statement)

    return bundle.to_json(), pub_key_pem, event_digest
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
import json
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import BaseModel, ConfigDict, Field, field_validator


REQUIRED_OWNER_AUTH_FIELDS = (
    "chain_id",
    "sequence_num",
    "prev_event_digest",
    "prev_lookup_hash",
    "event_digest",
)
OWNER_AUTH_ALGORITHM = "ecdsa-p384-sha384"


def canonical_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


class OwnerAuthorization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    signed_fields: list[str] = Field(
        min_length=len(REQUIRED_OWNER_AUTH_FIELDS),
        max_length=len(REQUIRED_OWNER_AUTH_FIELDS),
    )
    signature: str

    @field_validator("algorithm", "signature")
    @classmethod
    def _require_non_empty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("signed_fields")
    @classmethod
    def _validate_signed_fields(cls, value: list[str]) -> list[str]:
        if value != list(REQUIRED_OWNER_AUTH_FIELDS):
            raise ValueError(
                f"signed_fields must equal {list(REQUIRED_OWNER_AUTH_FIELDS)} in that order"
            )
        return value


def _authorization_message(
    chain_id: str,
    sequence_num: int,
    prev_event_digest: str | None,
    prev_lookup_hash: str | None,
    event_digest: str,
) -> bytes:
    payload = [
        ["chain_id", chain_id],
        ["sequence_num", sequence_num],
        ["prev_event_digest", prev_event_digest],
        ["prev_lookup_hash", prev_lookup_hash],
        ["event_digest", event_digest],
    ]
    return canonical_json(payload).encode("utf-8")


def sign_owner_authorization(
    private_key: ec.EllipticCurvePrivateKey,
    chain_id: str,
    sequence_num: int,
    prev_event_digest: str | None,
    prev_lookup_hash: str | None,
    event_digest: str,
) -> dict[str, Any]:
    signature = private_key.sign(
        _authorization_message(
            chain_id=chain_id,
            sequence_num=sequence_num,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            event_digest=event_digest,
        ),
        ec.ECDSA(hashes.SHA384()),
    )
    return OwnerAuthorization(
        algorithm=OWNER_AUTH_ALGORITHM,
        signed_fields=list(REQUIRED_OWNER_AUTH_FIELDS),
        signature=base64.b64encode(signature).decode("ascii"),
    ).model_dump()


def validate_owner_authorization_payload(payload: Any) -> OwnerAuthorization:
    if isinstance(payload, OwnerAuthorization):
        return payload
    return OwnerAuthorization.model_validate(payload)


def verify_owner_authorization(
    payload: Any,
    owner_pub_key_pem: str,
    chain_id: str,
    sequence_num: int,
    prev_event_digest: str | None,
    prev_lookup_hash: str | None,
    event_digest: str,
) -> bool:
    authorization = validate_owner_authorization_payload(payload)
    public_key = serialization.load_pem_public_key(owner_pub_key_pem.encode("utf-8"))
    if not isinstance(public_key, ec.EllipticCurvePublicKey):
        raise ValueError("owner public key must be an EC public key")

    signature = base64.b64decode(authorization.signature)
    try:
        public_key.verify(
            signature,
            _authorization_message(
                chain_id=chain_id,
                sequence_num=sequence_num,
                prev_event_digest=prev_event_digest,
                prev_lookup_hash=prev_lookup_hash,
                event_digest=event_digest,
            ),
            ec.ECDSA(hashes.SHA384()),
        )
    except InvalidSignature:
        return False
    return True


__all__ = [
    "OWNER_AUTH_ALGORITHM",
    "OwnerAuthorization",
    "REQUIRED_OWNER_AUTH_FIELDS",
    "sign_owner_authorization",
    "validate_owner_authorization_payload",
    "verify_owner_authorization",
]
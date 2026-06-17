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

import json
import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from tlog.digest import canonical_json


REQUIRED_OWNER_BOUND_FIELDS = (
    "chain_id",
    "sequence_num",
    "baseline_rtmr",
    "ccel_digest",
    "owner_pub_key",
)
OWNER_BINDING_ALGORITHM = "sha384"


class OwnerReportDataBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    bound_fields: list[str] = Field(
        min_length=len(REQUIRED_OWNER_BOUND_FIELDS),
        max_length=len(REQUIRED_OWNER_BOUND_FIELDS),
    )
    expected_value: str

    @field_validator("algorithm", "expected_value")
    @classmethod
    def _require_non_empty_string(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must be a non-empty string")
        return value

    @field_validator("bound_fields")
    @classmethod
    def _validate_bound_fields(cls, value: list[str]) -> list[str]:
        if value != list(REQUIRED_OWNER_BOUND_FIELDS):
            raise ValueError(
                f"bound_fields must equal {list(REQUIRED_OWNER_BOUND_FIELDS)} in that order"
            )
        return value


class ChainRootOwnerAttestation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    tee_type: Literal["tdx"]
    chain_id: str
    sequence_num: int = Field(ge=1)
    owner_pub_key: str
    baseline_rtmr: str | None = None
    ccel_digest: str | None = None
    generated_at: datetime
    quote: str
    report_data_binding: OwnerReportDataBinding
    quote_format: str | None = None

    @field_validator(
        "version",
        "chain_id",
        "owner_pub_key",
        "quote",
        "quote_format",
        mode="before",
    )
    @classmethod
    def _validate_strings(cls, value: Any) -> Any:
        if value is None:
            return value
        if not isinstance(value, str) or not value.strip():
            raise ValueError("must be a non-empty string")
        return value


def validate_chain_root_owner_attestation_payload(payload: Any) -> ChainRootOwnerAttestation:
    if isinstance(payload, ChainRootOwnerAttestation):
        return payload
    return ChainRootOwnerAttestation.model_validate(payload)


def canonicalize_chain_root_owner_attestation(payload: Any) -> str:
    attestation = validate_chain_root_owner_attestation_payload(payload)
    return canonical_json(attestation.model_dump(mode="json", exclude_none=True))


def compute_owner_attestation_expected_value(
    chain_id: str,
    sequence_num: int,
    baseline_rtmr: str | None,
    ccel_digest: str | None,
    owner_pub_key: str,
) -> str:
    bound_items = [
        ["chain_id", chain_id],
        ["sequence_num", sequence_num],
        ["baseline_rtmr", baseline_rtmr],
        ["ccel_digest", ccel_digest],
        ["owner_pub_key", owner_pub_key],
    ]
    payload = canonical_json(bound_items).encode("utf-8")
    return f"{OWNER_BINDING_ALGORITHM}:" + hashlib.sha384(payload).hexdigest()


__all__ = [
    "ChainRootOwnerAttestation",
    "OWNER_BINDING_ALGORITHM",
    "OwnerReportDataBinding",
    "REQUIRED_OWNER_BOUND_FIELDS",
    "canonical_json",
    "canonicalize_chain_root_owner_attestation",
    "compute_owner_attestation_expected_value",
    "validate_chain_root_owner_attestation_payload",
]
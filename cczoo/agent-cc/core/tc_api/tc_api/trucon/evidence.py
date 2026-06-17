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
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REQUIRED_BOUND_FIELDS = ("head_log_id",)
BINDING_ALGORITHM = "head_log_id_bytes"


def canonical_json(data: Any) -> str:
    return json.dumps(data, separators=(",", ":"), sort_keys=True, ensure_ascii=False)


class ReportDataBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    algorithm: str
    bound_fields: list[str] = Field(min_length=len(REQUIRED_BOUND_FIELDS), max_length=len(REQUIRED_BOUND_FIELDS))
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
        if value != list(REQUIRED_BOUND_FIELDS):
            raise ValueError(f"bound_fields must equal {list(REQUIRED_BOUND_FIELDS)} in that order")
        return value


class AttestedHeadEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    tee_type: Literal["tdx"]
    chain_id: str
    sequence_num: int = Field(ge=1)
    head_log_id: str
    mr_value: str
    generated_at: datetime
    quote: str
    report_data_binding: ReportDataBinding
    head_event_digest: str | None = None
    quote_format: str | None = None
    expires_at: datetime | None = None
    extensions: dict[str, Any] | None = None

    @field_validator(
        "version",
        "chain_id",
        "head_log_id",
        "mr_value",
        "quote",
        "head_event_digest",
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


def validate_attested_head_evidence_payload(payload: Any) -> AttestedHeadEvidence:
    if isinstance(payload, AttestedHeadEvidence):
        return payload
    return AttestedHeadEvidence.model_validate(payload)


def canonicalize_attested_head_evidence(payload: Any) -> str:
    evidence = validate_attested_head_evidence_payload(payload)
    return canonical_json(evidence.model_dump(mode="json", exclude_none=True))


def load_attested_head_evidence_json(payload: str) -> AttestedHeadEvidence:
    return validate_attested_head_evidence_payload(json.loads(payload))


def _is_hex_string(value: str) -> bool:
    if not value or len(value) % 2 != 0:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


def binding_payload_bytes_from_head_log_id(head_log_id: str) -> bytes:
    normalized = head_log_id.strip()
    if _is_hex_string(normalized):
        return bytes.fromhex(normalized)
    return normalized.encode("utf-8")


def encode_binding_expected_value(raw_bytes: bytes) -> str:
    return f"{BINDING_ALGORITHM}:" + raw_bytes.hex()


def decode_binding_expected_value(expected_value: str) -> bytes:
    prefix = f"{BINDING_ALGORITHM}:"
    if not expected_value.startswith(prefix):
        raise ValueError(f"expected_value must start with '{prefix}'")
    try:
        return bytes.fromhex(expected_value.removeprefix(prefix))
    except ValueError as exc:
        raise ValueError("expected_value must encode valid hex bytes") from exc


def compute_binding_expected_value(
    chain_id: str,
    sequence_num: int,
    head_log_id: str,
    mr_value: str,
) -> str:
    del chain_id, sequence_num, mr_value
    return encode_binding_expected_value(binding_payload_bytes_from_head_log_id(head_log_id))


__all__ = [
    "AttestedHeadEvidence",
    "BINDING_ALGORITHM",
    "binding_payload_bytes_from_head_log_id",
    "REQUIRED_BOUND_FIELDS",
    "ReportDataBinding",
    "ValidationError",
    "compute_binding_expected_value",
    "canonicalize_attested_head_evidence",
    "canonical_json",
    "decode_binding_expected_value",
    "encode_binding_expected_value",
    "load_attested_head_evidence_json",
    "validate_attested_head_evidence_payload",
]
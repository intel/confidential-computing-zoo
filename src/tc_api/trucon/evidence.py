import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

REQUIRED_BOUND_FIELDS = ("chain_id", "sequence_num", "head_log_id", "mr_value")


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


__all__ = [
    "AttestedHeadEvidence",
    "REQUIRED_BOUND_FIELDS",
    "ReportDataBinding",
    "ValidationError",
    "canonicalize_attested_head_evidence",
    "canonical_json",
    "load_attested_head_evidence_json",
    "validate_attested_head_evidence_payload",
]
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from tc_api.trucon.evidence import (
    REQUIRED_BOUND_FIELDS,
    canonicalize_attested_head_evidence,
    validate_attested_head_evidence_payload,
)


FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_valid_attested_head_evidence_fixture_is_accepted():
    payload = _load_fixture("attested_head_evidence_valid.json")

    evidence = validate_attested_head_evidence_payload(payload)

    assert evidence.version == "v1"
    assert evidence.tee_type == "tdx"
    assert evidence.report_data_binding.bound_fields == list(REQUIRED_BOUND_FIELDS)


def test_missing_required_field_is_rejected():
    payload = _load_fixture("attested_head_evidence_missing_required.json")

    with pytest.raises(ValidationError) as excinfo:
        validate_attested_head_evidence_payload(payload)

    assert "mr_value" in str(excinfo.value)


def test_incomplete_binding_metadata_is_rejected():
    payload = _load_fixture("attested_head_evidence_incomplete_binding.json")

    with pytest.raises(ValidationError) as excinfo:
        validate_attested_head_evidence_payload(payload)

    assert "bound_fields" in str(excinfo.value)


def test_canonicalization_omits_none_fields_and_is_sorted():
    payload = _load_fixture("attested_head_evidence_valid.json")
    payload["extensions"] = None
    payload["head_event_digest"] = None

    serialized = canonicalize_attested_head_evidence(payload)

    assert '"extensions"' not in serialized
    assert '"head_event_digest"' not in serialized
    assert serialized.index('"chain_id"') < serialized.index('"generated_at"')
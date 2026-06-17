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
from typing import Any, Dict, Optional

from fastapi import HTTPException

from .bundles import compute_record_lookup_hash
from .database import get_chain_records
from .owner_authorization import verify_owner_authorization
from .schemas import ChainEntryResult, ChainVerificationResponse


def record_is_baseline(record: Any) -> bool:
    payload = record["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return False
    return isinstance(payload, dict) and bool(payload.get("is_baseline"))


def record_payload_dict(record: Any) -> Optional[Dict[str, Any]]:
    payload = record["payload"]
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    return payload if isinstance(payload, dict) else None


def get_chain_owner_pub_key_from_records(records: list[Any]) -> Optional[str]:
    if not records:
        return None

    baseline = records[0]
    if not record_is_baseline(baseline):
        return None

    payload = record_payload_dict(baseline)
    if payload is None:
        return None
    if not isinstance(payload.get("owner_attestation"), dict):
        return None
    owner_pub_key = payload.get("pub_key")
    return owner_pub_key if isinstance(owner_pub_key, str) and owner_pub_key else None


def record_has_signed_predecessor_contract(record: Any) -> bool:
    sequence_num = record['sequence_num']
    return sequence_num > 1 and (
        ('prev_event_digest' in record.keys() and record['prev_event_digest'] is not None)
        or ('prev_lookup_hash' in record.keys() and record['prev_lookup_hash'] is not None)
    )


def classify_verify_chain_boundary(record: Any, records: list[Any]) -> Optional[str]:
    sequence_num = record['sequence_num']
    if sequence_num <= 1 or record_has_signed_predecessor_contract(record):
        return None

    lower_signed = any(
        other['sequence_num'] < sequence_num and record_has_signed_predecessor_contract(other)
        for other in records
    )
    if lower_signed:
        return "invalid"

    higher_signed = any(
        other['sequence_num'] > sequence_num and record_has_signed_predecessor_contract(other)
        for other in records
    )
    if higher_signed:
        return "degraded"

    return None


def verify_chain_records(chain_id: str, records: Optional[list[Any]] = None) -> ChainVerificationResponse:
    records = records if records is not None else get_chain_records(chain_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No records for chain '{chain_id}'")

    entries: list[ChainEntryResult] = []
    valid = True
    first_error_at: Optional[int] = None
    mr_verified = 0
    rekor_confirmed = 0
    rekor_pending = 0
    expected_seq = 1
    prev_mr: Optional[str] = None
    prev_confirmed_record: Optional[Any] = None
    baseline_error: Optional[str] = None
    rtmr_available = any(record['mr_value'] is not None for record in records)
    owner_pub_key = get_chain_owner_pub_key_from_records(records)

    if chain_id != 'default' and not record_is_baseline(records[0]):
        baseline_error = f"non-default chain '{chain_id}' does not begin with Event Log 0"
        valid = False
        first_error_at = records[0]['sequence_num']

    for record in records:
        seq = record['sequence_num']
        record_id = record['record_id']
        event_id = record['event_id']
        mr_value = record['mr_value']
        event_digest = record['event_digest'] if 'event_digest' in record.keys() else None
        rtmr_ext = bool(record['rtmr_extended'])
        is_confirmed = record['status'] == 'CONFIRMED' and record['log_id'] is not None
        error: Optional[str] = None
        mr_ok: Optional[bool] = None
        predecessor_ok: Optional[bool] = None
        predecessor_status: Optional[str] = None
        owner_ok: Optional[bool] = None
        owner_status: Optional[str] = None
        prev_event_digest = record['prev_event_digest'] if 'prev_event_digest' in record.keys() else None
        prev_lookup_hash = record['prev_lookup_hash'] if 'prev_lookup_hash' in record.keys() else None
        candidate_count: Optional[int] = None
        materialized_candidate_count: Optional[int] = None
        matched_candidate_count: Optional[int] = None
        boundary_status: Optional[str] = None
        payload = record_payload_dict(record)

        if baseline_error and seq == records[0]['sequence_num']:
            error = baseline_error

        if seq != expected_seq:
            error = f"sequence gap: expected {expected_seq}, got {seq}"
            if valid:
                valid = False
                first_error_at = seq

        if record_is_baseline(record):
            mr_ok = None
        elif mr_value is None or event_digest is None:
            mr_ok = None
        else:
            if prev_mr is not None:
                prev_bytes = bytes.fromhex(prev_mr)
            else:
                prev_bytes = b'\x00' * 48
            digest_bytes = bytes.fromhex(event_digest.removeprefix("sha384:"))
            expected_mr = hashlib.sha384(prev_bytes + digest_bytes).hexdigest()
            if mr_value == expected_mr:
                mr_ok = True
                mr_verified += 1
            else:
                mr_ok = False
                mr_error = f"RTMR mismatch: expected {expected_mr}, got {mr_value}"
                error = f"{error}; {mr_error}" if error else mr_error
                if valid:
                    valid = False
                    first_error_at = seq

        rekor_ok = is_confirmed
        if is_confirmed:
            rekor_confirmed += 1
        else:
            rekor_pending += 1

        if is_confirmed and prev_event_digest is None and prev_lookup_hash is None:
            boundary_status = classify_verify_chain_boundary(record, records)
            if boundary_status == "invalid":
                boundary_error = "signed predecessor contract regressed after reservation-backed replay began"
                error = f"{error}; {boundary_error}" if error else boundary_error
                if valid:
                    valid = False
                    first_error_at = seq

        if not rtmr_available:
            if not is_confirmed:
                predecessor_ok = None
                predecessor_status = "unverifiable"
                candidate_count = None
                materialized_candidate_count = None
                matched_candidate_count = None
            elif seq == 1 and prev_event_digest is None and prev_lookup_hash is None:
                predecessor_ok = True
                predecessor_status = "origin"
                candidate_count = 0
                materialized_candidate_count = 0
                matched_candidate_count = 0
            elif prev_event_digest is None and prev_lookup_hash is None:
                predecessor_ok = False if boundary_status == "invalid" else None
                predecessor_status = "unverifiable"
                candidate_count = 0
                materialized_candidate_count = 0
                matched_candidate_count = 0
                link_error = "signed predecessor contract unavailable for confirmed replayable record"
                if boundary_status == "invalid":
                    link_error = "signed predecessor contract regressed after reservation-backed replay began"
                elif boundary_status == "degraded":
                    link_error = "signed predecessor contract unavailable at legacy-to-reservation replay boundary"
                error = f"{error}; {link_error}" if error else link_error
            else:
                candidate_count = 1 if prev_confirmed_record is not None else 0
                materialized_candidate_count = candidate_count
                expected_digest = prev_confirmed_record['event_digest'] if prev_confirmed_record is not None else None
                expected_lookup_hash = compute_record_lookup_hash(prev_confirmed_record) if prev_confirmed_record is not None else None
                expected_sequence = prev_confirmed_record['sequence_num'] + 1 if prev_confirmed_record is not None else None
                predecessor_ok = (
                    prev_confirmed_record is not None
                    and seq == expected_sequence
                    and prev_event_digest == expected_digest
                    and prev_lookup_hash == expected_lookup_hash
                )
                matched_candidate_count = 1 if predecessor_ok else 0
                predecessor_status = "proven" if predecessor_ok else "missing"
                if candidate_count == 0:
                    predecessor_status = "missing"
                if not predecessor_ok:
                    link_error = (
                        f"signed predecessor mismatch: expected digest={expected_digest} lookup_hash={expected_lookup_hash}, "
                        f"got digest={prev_event_digest} lookup_hash={prev_lookup_hash}"
                    )
                    error = f"{error}; {link_error}" if error else link_error
                    if valid:
                        valid = False
                        first_error_at = seq

        if owner_pub_key is not None:
            if record_is_baseline(record):
                owner_ok = True
                owner_status = "origin"
            elif not is_confirmed:
                owner_ok = None
                owner_status = "unverifiable"
            else:
                owner_authorization = payload.get("owner_authorization") if payload is not None else None
                if owner_authorization is None:
                    owner_ok = False
                    owner_status = "missing"
                    owner_error = "owner authorization missing for confirmed record"
                else:
                    try:
                        owner_ok = verify_owner_authorization(
                            owner_authorization,
                            owner_pub_key_pem=owner_pub_key,
                            chain_id=chain_id,
                            sequence_num=seq,
                            prev_event_digest=prev_event_digest,
                            prev_lookup_hash=prev_lookup_hash,
                            event_digest=event_digest,
                        )
                    except Exception as exc:
                        owner_ok = False
                        owner_status = "invalid"
                        owner_error = f"owner authorization invalid: {exc}"
                    else:
                        if owner_ok:
                            owner_status = "proven"
                        else:
                            owner_status = "invalid"
                            owner_error = "owner authorization signature mismatch"

                if owner_ok is False:
                    error = f"{error}; {owner_error}" if error else owner_error
                    if valid:
                        valid = False
                        first_error_at = seq

        entries.append(ChainEntryResult(
            seq=seq,
            record_id=record_id,
            event_id=event_id,
            mr_ok=mr_ok,
            rekor_ok=rekor_ok,
            rtmr_extended=rtmr_ext,
            mr_value=mr_value,
            predecessor_ok=predecessor_ok,
            predecessor_status=predecessor_status,
            owner_ok=owner_ok,
            owner_status=owner_status,
            prev_event_digest=prev_event_digest,
            prev_lookup_hash=prev_lookup_hash,
            candidate_count=candidate_count,
            materialized_candidate_count=materialized_candidate_count,
            matched_candidate_count=matched_candidate_count,
            boundary_status=boundary_status,
            error=error,
        ))

        if mr_value is not None:
            prev_mr = mr_value
        if is_confirmed:
            prev_confirmed_record = record
        expected_seq = seq + 1

    head_mr = records[-1]['mr_value'] if records else None

    return ChainVerificationResponse(
        valid=valid,
        chain_id=chain_id,
        total_entries=len(records),
        mr_verified=mr_verified,
        rekor_confirmed=rekor_confirmed,
        rekor_pending=rekor_pending,
        rtmr_available=rtmr_available,
        head_mr_value=head_mr,
        first_error_at=first_error_at,
        entries=entries,
    )

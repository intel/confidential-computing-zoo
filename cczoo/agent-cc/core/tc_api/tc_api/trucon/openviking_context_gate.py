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
import hashlib
import json
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from .evidence import (
    canonicalize_attested_head_evidence,
    compute_binding_expected_value,
    validate_attested_head_evidence_payload,
)
from .schemas import OpenVikingEvidenceResponse


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _evidence_digest(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return "sha384:" + hashlib.sha384(encoded).hexdigest()


def _fetch_json(url: str, timeout: int = 10) -> Dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class ContextSendPolicy(BaseModel):
    target_url: str
    chain_id: str = "default"
    expected_policy_id: str = "openviking-context-send"
    expected_policy_version: Optional[str] = None
    expected_service_instance_id: Optional[str] = None
    expected_measurement_ref: Optional[str] = None
    freshness_ttl_seconds: int = 300
    subject_hash: Optional[str] = None
    scope_hash: Optional[str] = None


class ContextSendDecision(BaseModel):
    result: str
    decision_id: str
    operation: str = "send_context"
    verified_target: str = "openviking"
    policy_id: Optional[str] = None
    policy_version: Optional[str] = None
    evidence_digest: Optional[str] = None
    expires_at: Optional[str] = None
    reason: Optional[str] = None
    fail_closed: bool = False
    cache_hit: bool = False
    decision_record: Dict[str, Any] = Field(default_factory=dict)


@dataclass
class TrustCacheEntry:
    cache_key: str
    decision: ContextSendDecision
    expires_at: datetime


class InMemoryTrustCache:
    def __init__(self) -> None:
        self._entries: dict[str, TrustCacheEntry] = {}

    def get(self, cache_key: str, now: Optional[datetime] = None) -> Optional[ContextSendDecision]:
        now = now or _utcnow()
        entry = self._entries.get(cache_key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._entries.pop(cache_key, None)
            return None
        return entry.decision.model_copy(update={"cache_hit": True})

    def put(self, cache_key: str, decision: ContextSendDecision, expires_at: datetime) -> None:
        self._entries[cache_key] = TrustCacheEntry(cache_key=cache_key, decision=decision, expires_at=expires_at)


def build_cache_key(policy: ContextSendPolicy, evidence: OpenVikingEvidenceResponse) -> str:
    return "|".join(
        [
            policy.target_url.rstrip("/"),
            evidence.service_instance_id,
            evidence.measurement_ref,
            evidence.ledger_head_id,
            evidence.policy_version,
        ]
    )


def _build_decision_record(
    *,
    result: str,
    policy: ContextSendPolicy,
    evidence: Optional[OpenVikingEvidenceResponse],
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    record: Dict[str, Any] = {
        "operation": "send_context",
        "result": result,
        "target_url": policy.target_url.rstrip("/"),
    }
    if evidence is not None:
        record.update(
            {
                "policy_id": evidence.policy_id,
                "policy_version": evidence.policy_version,
                "evidence_digest": evidence.evidence_digest,
                "ledger_chain_id": evidence.ledger_chain_id,
                "ledger_head_id": evidence.ledger_head_id,
                "service_instance_id": evidence.service_instance_id,
                "expires_at": evidence.expires_at,
            }
        )
    if policy.subject_hash:
        record["subject_hash"] = policy.subject_hash
    if policy.scope_hash:
        record["scope_hash"] = policy.scope_hash
    if reason:
        record["reason"] = reason
    return record


def _deny(policy: ContextSendPolicy, reason: str, evidence: Optional[OpenVikingEvidenceResponse] = None) -> ContextSendDecision:
    return ContextSendDecision(
        result="deny",
        decision_id=f"cmem-deny-{uuid.uuid4().hex}",
        reason=reason,
        fail_closed=True,
        policy_id=evidence.policy_id if evidence is not None else policy.expected_policy_id,
        policy_version=evidence.policy_version if evidence is not None else policy.expected_policy_version,
        evidence_digest=evidence.evidence_digest if evidence is not None else None,
        expires_at=evidence.expires_at if evidence is not None else None,
        decision_record=_build_decision_record(result="deny", policy=policy, evidence=evidence, reason=reason),
    )


def _validate_evidence(policy: ContextSendPolicy, evidence: OpenVikingEvidenceResponse, now: datetime) -> Optional[str]:
    if evidence.policy_id != policy.expected_policy_id:
        return "policy_id_mismatch"
    if policy.expected_policy_version and evidence.policy_version != policy.expected_policy_version:
        return "policy_version_mismatch"
    if policy.expected_service_instance_id and evidence.service_instance_id != policy.expected_service_instance_id:
        return "service_instance_mismatch"
    if policy.expected_measurement_ref and evidence.measurement_ref != policy.expected_measurement_ref:
        return "measurement_mismatch"

    try:
        generated_at = _parse_timestamp(evidence.generated_at)
        expires_at = _parse_timestamp(evidence.expires_at)
    except ValueError:
        return "invalid_timestamp"

    if expires_at <= now:
        return "evidence_expired"
    if generated_at > now + timedelta(seconds=5):
        return "evidence_from_future"

    try:
        attested = validate_attested_head_evidence_payload(evidence.attested_head_evidence)
    except Exception:
        return "attested_evidence_invalid"

    if attested.chain_id != evidence.ledger_chain_id:
        return "ledger_chain_mismatch"
    if attested.head_log_id != evidence.ledger_head_id:
        return "ledger_head_mismatch"
    if attested.mr_value != evidence.measurement_ref:
        return "measurement_binding_mismatch"

    expected_value = compute_binding_expected_value(
        chain_id=attested.chain_id,
        sequence_num=attested.sequence_num,
        head_log_id=attested.head_log_id,
        mr_value=attested.mr_value,
    )
    if attested.report_data_binding.expected_value != expected_value:
        return "binding_expected_value_mismatch"

    recomputed_digest = _evidence_digest(evidence.attested_head_evidence)
    if evidence.evidence_digest != recomputed_digest:
        return "evidence_digest_mismatch"
    return None


def verify_context_send_payload(
    payload: Dict[str, Any],
    policy: ContextSendPolicy,
    *,
    cache: Optional[InMemoryTrustCache] = None,
    now: Optional[datetime] = None,
) -> ContextSendDecision:
    now = now or _utcnow()
    try:
        evidence = OpenVikingEvidenceResponse.model_validate(payload)
    except Exception:
        return _deny(policy, "missing_required_claims")

    cache_key = build_cache_key(policy, evidence)
    if cache is not None:
        cached = cache.get(cache_key, now=now)
        if cached is not None:
            return cached

    reason = _validate_evidence(policy, evidence, now)
    if reason:
        return _deny(policy, reason, evidence)

    allowed_until = min(
        _parse_timestamp(evidence.expires_at),
        now + timedelta(seconds=policy.freshness_ttl_seconds),
    )
    decision = ContextSendDecision(
        result="allow",
        decision_id=f"cmem-allow-{uuid.uuid4().hex}",
        policy_id=evidence.policy_id,
        policy_version=evidence.policy_version,
        evidence_digest=evidence.evidence_digest,
        expires_at=allowed_until.isoformat(),
        decision_record=_build_decision_record(result="allow", policy=policy, evidence=evidence),
    )
    if cache is not None:
        cache.put(cache_key, decision, allowed_until)
    return decision


def verify_context_send(
    policy: ContextSendPolicy,
    *,
    cache: Optional[InMemoryTrustCache] = None,
    now: Optional[datetime] = None,
    fetcher: Any = _fetch_json,
) -> ContextSendDecision:
    evidence_url = f"{policy.target_url.rstrip('/')}/confidential/evidence"
    try:
        payload = fetcher(evidence_url)
    except urllib.error.URLError:
        return _deny(policy, "verification_unavailable")
    except Exception:
        return _deny(policy, "verification_unavailable")
    return verify_context_send_payload(payload, policy, cache=cache, now=now)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify OpenViking before sending context")
    parser.add_argument("target_url")
    parser.add_argument("--chain-id", default="default")
    parser.add_argument("--policy-id", default="openviking-context-send")
    parser.add_argument("--policy-version")
    parser.add_argument("--service-instance-id")
    parser.add_argument("--measurement-ref")
    parser.add_argument("--subject-hash")
    parser.add_argument("--scope-hash")
    parser.add_argument("--ttl-seconds", type=int, default=300)
    args = parser.parse_args()

    policy = ContextSendPolicy(
        target_url=args.target_url,
        chain_id=args.chain_id,
        expected_policy_id=args.policy_id,
        expected_policy_version=args.policy_version,
        expected_service_instance_id=args.service_instance_id,
        expected_measurement_ref=args.measurement_ref,
        freshness_ttl_seconds=args.ttl_seconds,
        subject_hash=args.subject_hash,
        scope_hash=args.scope_hash,
    )
    decision = verify_context_send(policy)
    print(json.dumps(decision.model_dump(mode="json", exclude_none=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
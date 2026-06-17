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

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class CommitRequest(BaseModel):
    bundle: str
    chain_id: str
    event_digest: str
    event_id: Optional[str] = None
    intent_token: Optional[str] = None
    idempotency_key: Optional[str] = None
    instance_id: Optional[str] = None
    identity_token: Optional[str] = None
    owner_authorization: Optional[Dict[str, Any]] = None


class CommitResponse(BaseModel):
    record_id: str
    sequence_num: int
    mr_value: Optional[str] = None
    prev_mr_value: Optional[str] = None


class ChainStateResponse(BaseModel):
    chain_id: str
    head_record_id: Optional[str] = None
    head_log_id: Optional[str] = None
    sequence_num: int = 0
    mr_value: Optional[str] = None
    updated_at: Optional[str] = None


class CommitQueueStatusResponse(BaseModel):
    has_queued_records: bool
    queued_record_count: int
    next_record_id: Optional[str] = None
    submitting_count: int = 0
    failed_retryable_count: int = 0
    failed_terminal_count: int = 0
    total_retry_count: int = 0


class LatestStateResponse(BaseModel):
    latest_confirmed_log_id: Optional[str] = None
    pending_record_count: int = 0
    pending_event_ids: List[str] = Field(default_factory=list)
    latest_mr_value: Optional[str] = None


class InitChainBaselineResponse(BaseModel):
    rtmr_value: Optional[str] = None
    ccel_digest: Optional[str] = None
    ccel_eventlog_b64: Optional[str] = None
    init_token: str


class InitChainRequest(BaseModel):
    chain_id: str
    init_token: str
    intent_token: str
    signed_bundle: str
    pub_key: str


class CommitIntentReserveRequest(BaseModel):
    chain_id: str
    idempotency_key: Optional[str] = None
    is_baseline: bool = False


class CommitIntentReserveResponse(BaseModel):
    intent_token: Optional[str] = None
    chain_id: str
    sequence_num: int
    prev_event_digest: Optional[str] = None
    prev_lookup_hash: Optional[str] = None
    expires_at: Optional[str] = None
    committed: bool = False
    record_id: Optional[str] = None


class InitChainResponse(BaseModel):
    record_id: str
    sequence_num: int


class ChainEntryResult(BaseModel):
    seq: int
    record_id: str
    event_id: Optional[str] = None
    mr_ok: Optional[bool] = None
    rekor_ok: bool
    rtmr_extended: bool
    mr_value: Optional[str] = None
    predecessor_ok: Optional[bool] = None
    predecessor_status: Optional[str] = None
    owner_ok: Optional[bool] = None
    owner_status: Optional[str] = None
    prev_event_digest: Optional[str] = None
    prev_lookup_hash: Optional[str] = None
    candidate_count: Optional[int] = None
    materialized_candidate_count: Optional[int] = None
    matched_candidate_count: Optional[int] = None
    boundary_status: Optional[str] = None
    error: Optional[str] = None


class ChainVerificationResponse(BaseModel):
    valid: bool
    chain_id: str
    total_entries: int
    mr_verified: int
    rekor_confirmed: int
    rekor_pending: int
    rtmr_available: bool
    head_mr_value: Optional[str] = None
    first_error_at: Optional[int] = None
    entries: list[ChainEntryResult]


class InstanceSummary(BaseModel):
    instance_id: str
    first_event_at: Optional[str] = None
    last_event_at: Optional[str] = None
    event_count: int


class EventSummary(BaseModel):
    record_id: str
    event_id: Optional[str] = None
    sequence_num: int
    status: str
    created_at: Optional[str] = None
    instance_id: Optional[str] = None


class EvidenceErrorResponse(BaseModel):
    detail: str


class OpenVikingEvidenceResponse(BaseModel):
    kind: Literal["openviking-confidential-evidence"] = "openviking-confidential-evidence"
    chain_id: str
    deployment_id: str
    service_instance_id: str
    tee_type: str
    measurement_ref: str
    ledger_chain_id: str
    ledger_head_id: str
    evidence_digest: str
    generated_at: str
    expires_at: str
    policy_id: str
    policy_version: str
    egress_mode: str
    privacy_restore_policy: str
    attested_head_evidence: Dict[str, Any]


class OpenVikingPostureResponse(BaseModel):
    kind: Literal["openviking-confidential-posture"] = "openviking-confidential-posture"
    chain_id: str
    deployment_id: str
    service_instance_id: str
    tee_type: str
    policy_id: str
    policy_version: str
    egress_mode: str
    privacy_restore_policy: str
    generated_at: str
    has_confirmed_ledger_head: bool
    latest_ledger_head_id: Optional[str] = None
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
import hashlib
from typing import Any, Dict, List, Optional

from tc_api.verification_profiles import evaluate_profiles


def normalize_replay_entries(immutable_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "index": entry.get("index"),
            "event_id": entry.get("event_id"),
            "event_type": entry.get("event_type"),
            "sequence_num": entry.get("sequence_num"),
            "digest": entry.get("digest"),
            "created": entry.get("created"),
            "prev_event_digest": entry.get("prev_event_digest"),
            "prev_lookup_hash": entry.get("prev_lookup_hash"),
            "predecessor_ok": entry.get("predecessor_ok"),
            "owner_ok": entry.get("owner_ok"),
            "candidate_count": entry.get("candidate_count"),
            "materialized_candidate_count": entry.get("materialized_candidate_count"),
            "matched_candidate_count": entry.get("matched_candidate_count"),
            "predecessor_status": entry.get("predecessor_status"),
            "owner_status": entry.get("owner_status"),
            "boundary_status": entry.get("boundary_status"),
            "public_history_ok": entry.get("public_history_ok"),
            "public_history_status": entry.get("public_history_status"),
            "replay_provenance": entry.get("replay_provenance"),
            "history_materialization_provenance": entry.get("history_materialization_provenance"),
            "predicate_entries": entry.get("predicate_entries", []),
            "subject_names": entry.get("subject_names", []),
            "signer_identity": entry.get("signer_identity"),
            "signer_identity_match": entry.get("signer_identity_match"),
            "errors": entry.get("errors", []),
        }
        for entry in immutable_entries
    ]


def build_diagnostics(result: Dict[str, Any]) -> Dict[str, Any]:
    replay = result.get("replay") or {}
    fallback = result.get("fallback") or {}
    attested_head = result.get("attested_head") or {}
    replay_entries = replay.get("entries") or []
    fallback_entries = fallback.get("entries") or []

    entry_status_counts: Dict[str, int] = {}
    first_entry_issue = None
    for entry in replay_entries:
        predecessor_status = entry.get("predecessor_status") or "unknown"
        entry_status_counts[predecessor_status] = entry_status_counts.get(predecessor_status, 0) + 1
        if first_entry_issue is None and (
            entry.get("predecessor_ok") is False
            or entry.get("public_history_ok") is False
            or entry.get("boundary_status") is not None
            or entry.get("errors")
        ):
            first_entry_issue = {
                "index": entry.get("index"),
                "event_id": entry.get("event_id"),
                "sequence_num": entry.get("sequence_num"),
                "predecessor_status": entry.get("predecessor_status"),
                "public_history_status": entry.get("public_history_status"),
                "boundary_status": entry.get("boundary_status"),
                "history_materialization_provenance": entry.get("history_materialization_provenance"),
                "errors": entry.get("errors", []),
            }

    fallback_owner_status_counts: Dict[str, int] = {}
    fallback_first_entry_issue = None
    for entry in fallback_entries:
        owner_status = entry.get("owner_status") or "unknown"
        fallback_owner_status_counts[owner_status] = fallback_owner_status_counts.get(owner_status, 0) + 1
        if fallback_first_entry_issue is None and (
            entry.get("owner_ok") is False
            or owner_status not in {"unknown", "origin", "proven", None}
            or entry.get("error")
        ):
            fallback_first_entry_issue = {
                "seq": entry.get("seq"),
                "event_id": entry.get("event_id"),
                "owner_ok": entry.get("owner_ok"),
                "owner_status": entry.get("owner_status"),
                "predecessor_status": entry.get("predecessor_status"),
                "error": entry.get("error"),
            }

    return {
        "replay": {
            "reachable": replay.get("reachable"),
            "success": replay.get("success"),
            "provenance_status": (replay.get("provenance") or {}).get("status"),
            "entry_status_counts": entry_status_counts,
            "first_entry_issue": first_entry_issue,
            "event_log0_audit": collect_event_log0_audit(replay_entries),
        },
        "attested_head": {
            "present": attested_head.get("present"),
            "valid": attested_head.get("valid"),
            "matches_replay": attested_head.get("matches_replay"),
            "errors": attested_head.get("errors", []),
        },
        "fallback": {
            "reachable": fallback.get("reachable"),
            "valid": fallback.get("valid"),
            "rtmr_available": fallback.get("rtmr_available"),
            "owner_status_counts": fallback_owner_status_counts,
            "first_entry_issue": fallback_first_entry_issue,
        },
        "first_error": (result.get("errors") or [None])[0],
    }


def attach_profile_results(result: Dict[str, Any]) -> Dict[str, Any]:
    replay_entries = result.get("entries", [])
    profiles = evaluate_profiles(replay_entries)
    result["profiles"] = profiles
    result["diagnostics"] = build_diagnostics(result)
    return result


def summarize_replay_rollout(entries: List[Dict[str, Any]]) -> tuple[str, str]:
    boundary_statuses = [entry.get("boundary_status") for entry in entries if entry.get("boundary_status")]
    if "invalid" in boundary_statuses:
        return "invalid", "reservation-backed replay regressed to incompatible legacy linkage"
    if "degraded" in boundary_statuses:
        return "degraded", "mixed-regime migration state; replay visibility exists but continuous reservation-backed predecessor proof is unavailable across the full history"
    return "supported", "continuous reservation-backed predecessor proof is available for the replayed history"


def summarize_replay_provenance(entries: List[Dict[str, Any]]) -> tuple[str, str]:
    public_history_statuses = [entry.get("public_history_status") for entry in entries if entry.get("public_history_status")]
    materialization_sources = [
        entry.get("history_materialization_provenance")
        for entry in entries
        if entry.get("history_materialization_provenance")
    ]
    if not entries:
        return "unavailable", "no immutable replay entries were available"
    if any(status == "cache-assisted" for status in public_history_statuses):
        return "unsupported", "historical replay facts depended on process-local cache rather than Rekor-auditable materialization"
    if any(status in {"unmaterialized", "baseline-missing"} for status in public_history_statuses):
        return "degraded", "public Rekor materialization did not expose all verifier-critical historical facts"
    if any(source == "attestation-storage" for source in materialization_sources):
        return "attestation-storage", "historical continuity required Rekor-hosted attestation materialization in addition to public Rekor inclusion proof"
    if any(source == "mirror" for source in materialization_sources):
        return "mirrored", "historical continuity required mirrored bundle materialization in addition to public Rekor inclusion proof"
    return "public", "historical continuity and baseline origin were derived from publicly materialized replay data"


def compute_verification_tier(provenance_status: str, attested_valid: bool) -> str:
    if provenance_status == "mirrored" and attested_valid:
        return "public+mirrored+attested"
    if provenance_status == "mirrored":
        return "public+mirrored"
    if provenance_status == "attestation-storage":
        return "public+attestation-storage"
    return "public-only"


def entry_value(predicate_entries: List[Dict[str, Any]], key: str) -> Optional[str]:
    for entry in predicate_entries:
        if isinstance(entry, dict) and entry.get("key") == key:
            value = entry.get("value")
            return value if isinstance(value, str) else None
    return None


def collect_event_log0_audit(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    audit: Dict[str, Any] = {
        "present": False,
        "event_id": None,
        "chain_id": None,
        "baseline_rtmr": None,
        "ccel_digest": None,
        "ccel_eventlog_b64_present": False,
        "ccel_eventlog_b64_chars": None,
        "ccel_eventlog_decodable": None,
        "ccel_eventlog_bytes": None,
    }
    if not entries:
        return audit

    baseline_entry = entries[0]
    predicate_entries = baseline_entry.get("predicate_entries") or []
    ccel_eventlog_b64 = entry_value(predicate_entries, "ccel_eventlog_b64")
    audit.update(
        {
            "present": baseline_entry.get("event_type") == "chain.init",
            "event_id": baseline_entry.get("event_id"),
            "chain_id": baseline_entry.get("chain_id"),
            "baseline_rtmr": entry_value(predicate_entries, "baseline_rtmr"),
            "ccel_digest": entry_value(predicate_entries, "ccel_digest"),
            "ccel_eventlog_b64_present": ccel_eventlog_b64 is not None,
            "ccel_eventlog_b64_chars": len(ccel_eventlog_b64) if ccel_eventlog_b64 is not None else None,
        }
    )
    if ccel_eventlog_b64 is None:
        return audit

    try:
        decoded = base64.b64decode(ccel_eventlog_b64, validate=True)
    except Exception:
        audit["ccel_eventlog_decodable"] = False
        audit["ccel_eventlog_bytes"] = None
        return audit

    audit["ccel_eventlog_decodable"] = True
    audit["ccel_eventlog_bytes"] = len(decoded)
    return audit


def derive_replay_chain_state(immutable_result: Dict[str, Any]) -> Dict[str, Any]:
    immutable_data = immutable_result.get("details") or {}
    entries = list(reversed(immutable_data.get("entries", [])))
    chain_id = immutable_data.get("chain_id")
    derived = {
        "chain_id": chain_id,
        "sequence_num": len(entries),
        "head_log_id": immutable_result.get("head_log_id"),
        "mr_value": None,
        "head_event_digest": entries[-1].get("digest") if entries else None,
        "baseline_rtmr": None,
        "errors": [],
    }
    if not entries:
        derived["errors"].append("Immutable replay returned no entries")
        return derived

    first_entry = entries[0]
    baseline_entries = first_entry.get("predicate_entries") or []
    if chain_id != "default" and first_entry.get("event_type") != "chain.init":
        derived["errors"].append(f"Immutable replay for non-default chain '{chain_id}' did not begin with Event Log 0")
        return derived

    baseline_rtmr = entry_value(baseline_entries, "baseline_rtmr")
    if not baseline_rtmr or baseline_rtmr == "null":
        derived["errors"].append("Immutable replay did not expose a usable Event Log 0 baseline_rtmr")
        return derived

    derived["baseline_rtmr"] = baseline_rtmr
    current_mr = baseline_rtmr
    for entry in entries[1:]:
        digest = entry.get("digest")
        if not isinstance(digest, str) or not digest.startswith("sha384:"):
            derived["errors"].append(
                f"Immutable replay entry '{entry.get('event_id')}' is missing a replayable digest"
            )
            return derived
        current_mr = hashlib.sha384(
            bytes.fromhex(current_mr) + bytes.fromhex(digest.removeprefix("sha384:"))
        ).hexdigest()

    derived["mr_value"] = current_mr
    return derived

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

import logging
from typing import Any, Dict, List, Optional

from ..trucon.owner_authorization import verify_owner_authorization
from tlog.digest import canonical_json

logger = logging.getLogger(__name__)


from .baseline import (
    _entry_has_required_history_fields,
    _entry_has_event_log0_baseline,
    _predicate_entry_value,
    _replay_owner_pub_key,
)
from .rekor_decode import (
    _decode_attestation_payload,
    _decode_dsse_payload,
    _decode_rekor_body,
    _extract_committed_payload_hash,
    _extract_signer_identity,
)

def _normalize_verification_entry(entry: Dict[str, Any], index: int, expected_identity: Optional[str]) -> Dict[str, Any]:
    body = _decode_rekor_body(entry)
    payload = _decode_dsse_payload(body)
    payload_hash = _extract_committed_payload_hash(body)
    attestation_error = None
    replay_provenance = entry.get("_tc_replay_provenance", "public")
    if not payload:
        payload, attestation_error = _decode_attestation_payload(entry, payload_hash)
        if payload and replay_provenance == "public":
            replay_provenance = "attestation-storage"
    predicate = payload.get("predicate", {}) if isinstance(payload, dict) else {}
    subject = payload.get("subject", []) if isinstance(payload, dict) else []
    subject_names = [item.get("name") for item in subject if isinstance(item, dict) and item.get("name")]
    signer_identity = _extract_signer_identity(entry)
    signer_match = None if expected_identity is None else signer_identity == expected_identity

    errors = []
    if attestation_error is not None:
        errors.append(attestation_error)

    history_materialization_provenance = "public"
    if replay_provenance in {"attestation-storage", "mirror"}:
        history_materialization_provenance = replay_provenance

    return {
        "index": index,
        "entry_id": entry.get("log_id") or entry.get("uuid") or entry.get("entryUUID"),
        "subject_names": subject_names,
        "event_id": predicate.get("event_id"),
        "event_type": predicate.get("event_type"),
        "chain_id": predicate.get("chain_id"),
        "sequence_num": predicate.get("sequence_num"),
        "digest": predicate.get("digest"),
        "predicate_entries": predicate.get("entries", []),
        "owner_authorization": predicate.get("owner_authorization") or payload.get("owner_authorization"),
        "created": predicate.get("created"),
        "prev_event_digest": predicate.get("prev_event_digest"),
        "prev_lookup_hash": predicate.get("prev_lookup_hash"),
        "payload_hash": payload_hash,
        "candidate_count": None,
        "materialized_candidate_count": None,
        "matched_candidate_count": None,
        "predecessor_ok": None,
        "predecessor_status": None,
        "public_history_ok": None,
        "public_history_status": None,
        "replay_provenance": replay_provenance,
        "history_materialization_provenance": history_materialization_provenance,
        "prev_log_id": predicate.get("prev_log_id") or payload.get("prev_log_id"),
        "signer_identity": signer_identity,
        "signer_identity_match": signer_match,
        "included": signer_match is not False,
        "errors": errors,
    }
def _annotate_owner_verification(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    owner_pub_key = _replay_owner_pub_key(entries)
    if not owner_pub_key:
        return [dict(entry) for entry in entries]

    annotated: List[Dict[str, Any]] = []
    for entry in entries:
        current = dict(entry)
        if current.get("event_type") == "chain.init" and current.get("sequence_num") == 1:
            current["owner_ok"] = True
            current["owner_status"] = "origin"
            annotated.append(current)
            continue

        owner_authorization = current.get("owner_authorization")
        if owner_authorization is None:
            current["owner_ok"] = False
            current["owner_status"] = "missing"
            current.setdefault("errors", []).append("Owner authorization missing for replayed record")
            annotated.append(current)
            continue

        try:
            owner_ok = verify_owner_authorization(
                owner_authorization,
                owner_pub_key_pem=owner_pub_key,
                chain_id=current.get("chain_id"),
                sequence_num=current.get("sequence_num"),
                prev_event_digest=current.get("prev_event_digest"),
                prev_lookup_hash=current.get("prev_lookup_hash"),
                event_digest=current.get("digest"),
            )
        except Exception as exc:
            current["owner_ok"] = False
            current["owner_status"] = "invalid"
            current.setdefault("errors", []).append(f"Owner authorization invalid: {exc}")
            annotated.append(current)
            continue

        current["owner_ok"] = owner_ok
        current["owner_status"] = "proven" if owner_ok else "invalid"
        if not owner_ok:
            current.setdefault("errors", []).append("Owner authorization signature mismatch")
        annotated.append(current)

    return annotated
def _annotate_delegation_verification(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Annotate each entry with delegation_status.

    Delegation events (event_type ``session.delegation``) are marked as
    ``origin``.  Subsequent events referencing a ``delegation_id`` are
    validated against the delegation's scope and expiry.  Events with no
    delegation context are marked ``not_applicable``.
    """
    from datetime import datetime

    # Build a map of delegation_id → delegation metadata from delegation events
    delegation_map: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if entry.get("event_type") == "session.delegation":
            did = entry.get("delegation_id")
            if did:
                delegation_map[did] = {
                    "scope": entry.get("scope", []),
                    "expires_at": entry.get("expires_at"),
                    "signer_identity": entry.get("signer_identity"),
                }

    annotated: List[Dict[str, Any]] = []
    for entry in entries:
        current = dict(entry)

        if current.get("event_type") == "session.delegation":
            current["delegation_status"] = "origin"
            annotated.append(current)
            continue

        delegation_id = current.get("delegation_id")
        if not delegation_id:
            current["delegation_status"] = "not_applicable"
            annotated.append(current)
            continue

        deleg = delegation_map.get(delegation_id)
        if deleg is None:
            current["delegation_status"] = "missing"
            current.setdefault("errors", []).append(
                f"Referenced delegation_id '{delegation_id}' not found in chain"
            )
            annotated.append(current)
            continue

        # Check TTL
        expires_at_str = deleg.get("expires_at")
        event_created = current.get("created")
        if expires_at_str and event_created:
            try:
                if event_created > expires_at_str:
                    current["delegation_status"] = "expired"
                    current.setdefault("errors", []).append(
                        f"Event created after delegation expiry ({expires_at_str})"
                    )
                    annotated.append(current)
                    continue
            except Exception:
                pass

        # Check scope
        scope = deleg.get("scope", [])
        event_type = current.get("event_type", "")
        # Extract operation from event_type like "docker_pull" → "pull"
        op = event_type.split("_", 1)[1] if "_" in event_type else event_type
        if scope and op not in scope:
            current["delegation_status"] = "scope_violation"
            current.setdefault("errors", []).append(
                f"Operation '{op}' not in delegation scope {scope}"
            )
            annotated.append(current)
            continue

        current["delegation_status"] = "proven"
        annotated.append(current)

    return annotated
def _entry_matches_chain(entry: Dict[str, Any], chain_id: str, subject_name: str) -> bool:
    if entry.get("chain_id") == chain_id:
        return True
    subject_names = entry.get("subject_names") or []
    if not entry.get("chain_id") and not subject_names:
        return True
    return subject_name in subject_names
def _classify_public_history_status(entry: Dict[str, Any]) -> Optional[str]:
    if entry.get("replay_provenance") == "cache-assisted":
        return "cache-assisted"
    if not _entry_has_required_history_fields(entry):
        return "unmaterialized"
    if not _entry_has_event_log0_baseline(entry):
        return "baseline-missing"
    return None
def _candidate_identity(candidate: Dict[str, Any]) -> str:
    entry_id = candidate.get("entry_id")
    payload_hash = candidate.get("payload_hash")
    return f"{entry_id}|{payload_hash}"
def _summarize_replay_candidate(entry: Dict[str, Any]) -> Dict[str, Any]:
    body = _decode_rekor_body(entry)
    payload = _decode_dsse_payload(body)
    predicate = payload.get("predicate", {}) if isinstance(payload, dict) else {}
    return {
        "entry_id": entry.get("entry_id") or entry.get("log_id") or entry.get("uuid") or entry.get("entryUUID"),
        "sequence_num": predicate.get("sequence_num") if isinstance(predicate, dict) else entry.get("sequence_num"),
        "event_id": predicate.get("event_id") if isinstance(predicate, dict) else entry.get("event_id"),
        "chain_id": predicate.get("chain_id") if isinstance(predicate, dict) else entry.get("chain_id"),
        "digest": predicate.get("digest") if isinstance(predicate, dict) else entry.get("digest"),
        "payload_hash": entry.get("payload_hash") or _extract_committed_payload_hash(body),
        "replay_provenance": entry.get("_tc_replay_provenance") or entry.get("replay_provenance") or "public",
        "has_decodable_payload": _decode_dsse_payload(body) != {},
        "has_attestation": entry.get("attestation") is not None,
        "body_kind": body.get("kind") if isinstance(body, dict) else None,
        "body_spec_keys": sorted((body.get("spec") or {}).keys()) if isinstance(body, dict) and isinstance(body.get("spec"), dict) else [],
        "errors": entry.get("errors", []),
    }
def _summarize_normalized_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "entry_id": candidate.get("entry_id"),
        "sequence_num": candidate.get("sequence_num"),
        "event_id": candidate.get("event_id"),
        "chain_id": candidate.get("chain_id"),
        "digest": candidate.get("digest"),
        "payload_hash": candidate.get("payload_hash"),
        "prev_lookup_hash": candidate.get("prev_lookup_hash"),
        "prev_event_digest": candidate.get("prev_event_digest"),
        "replay_provenance": candidate.get("replay_provenance"),
        "history_materialization_provenance": candidate.get("history_materialization_provenance"),
        "public_history_status": candidate.get("public_history_status"),
        "errors": candidate.get("errors", []),
    }
def _candidate_quality(candidate: Dict[str, Any]) -> tuple[int, int, int, int]:
    materialized = int(
        candidate.get("sequence_num") is not None
        and candidate.get("digest") is not None
        and candidate.get("payload_hash") is not None
    )
    provenance = candidate.get("replay_provenance")
    provenance_rank = {
        "mirror": 3,
        "attestation-storage": 2,
        "public": 1,
        "cache-assisted": 0,
    }.get(provenance, 0)
    has_chain_id = int(candidate.get("chain_id") is not None)
    fewer_errors = -len(candidate.get("errors") or [])
    return materialized, provenance_rank, has_chain_id, fewer_errors
def _matched_predecessor_contract(candidate: Dict[str, Any]) -> tuple[Any, Any, Any, Any]:
    return (
        candidate.get("chain_id"),
        candidate.get("sequence_num"),
        candidate.get("digest"),
        candidate.get("payload_hash"),
    )
def _has_signed_predecessor_contract(entry: Dict[str, Any]) -> bool:
    sequence_num = entry.get("sequence_num")
    return isinstance(sequence_num, int) and sequence_num > 1 and (
        entry.get("prev_event_digest") is not None or entry.get("prev_lookup_hash") is not None
    )
def _classify_replay_boundary(current: Dict[str, Any], entries: List[Dict[str, Any]]) -> Optional[str]:
    sequence_num = current.get("sequence_num")
    if not isinstance(sequence_num, int) or sequence_num <= 1:
        return None
    if _has_signed_predecessor_contract(current):
        return None

    lower_signed = any(
        _has_signed_predecessor_contract(entry) and entry.get("sequence_num") < sequence_num
        for entry in entries
    )
    if lower_signed:
        return "invalid"

    higher_signed = any(
        _has_signed_predecessor_contract(entry) and entry.get("sequence_num") > sequence_num
        for entry in entries
    )
    if higher_signed:
        return "degraded"

    return None
def _materialize_predecessor_candidates(
    current: Dict[str, Any],
    entries: List[Dict[str, Any]],
    immutable_log: Any,
) -> tuple[List[Dict[str, Any]], Optional[str]]:
    payload_hash = current.get("prev_lookup_hash")
    if not isinstance(payload_hash, str) or not payload_hash:
        return [], None

    candidate_sources: List[Dict[str, Any]] = []
    local_candidates: List[Dict[str, Any]] = []
    discovered_raw_summaries: List[Dict[str, Any]] = []
    normalized_discovered_summaries: List[Dict[str, Any]] = []
    for entry in entries:
        if entry is current:
            continue
        if entry.get("payload_hash") == payload_hash:
            local_candidate = dict(entry)
            candidate_sources.append(local_candidate)
            local_candidates.append(_summarize_normalized_candidate(local_candidate))

    finder = getattr(immutable_log, "find_entries_by_payload_hash", None)
    if callable(finder):
        try:
            discovered = finder(payload_hash)
        except Exception as exc:
            return candidate_sources, str(exc)
        for raw_entry in discovered or []:
            if isinstance(raw_entry, dict):
                discovered_raw_summaries.append(_summarize_replay_candidate(raw_entry))
            normalized = _normalize_verification_entry(raw_entry, 0, None)
            candidate_sources.append(normalized)
            normalized_discovered_summaries.append(_summarize_normalized_candidate(normalized))

    if current.get("sequence_num") == 3:
        logger.info(
            "replay_predecessor_candidates=%s",
            canonical_json(
                {
                    "chain_id": current.get("chain_id"),
                    "current_event_id": current.get("event_id"),
                    "current_sequence_num": current.get("sequence_num"),
                    "prev_lookup_hash": payload_hash,
                    "local_candidate_count": len(local_candidates),
                    "local_candidates": local_candidates,
                    "discovered_raw_candidate_count": len(discovered_raw_summaries),
                    "discovered_raw_candidates": discovered_raw_summaries,
                    "normalized_discovered_candidate_count": len(normalized_discovered_summaries),
                    "normalized_discovered_candidates": normalized_discovered_summaries,
                }
            ),
        )

    deduped_by_key: Dict[str, Dict[str, Any]] = {}
    for candidate in candidate_sources:
        candidate_key = _candidate_identity(candidate)
        existing = deduped_by_key.get(candidate_key)
        if existing is None or _candidate_quality(candidate) > _candidate_quality(existing):
            deduped_by_key[candidate_key] = candidate
    deduped = list(deduped_by_key.values())
    return deduped, None
def _annotate_predecessor_verification(entries: List[Dict[str, Any]], immutable_log: Any) -> List[Dict[str, Any]]:
    """Annotate head->tail replay entries with signed predecessor verification details."""
    annotated: List[Dict[str, Any]] = []

    require_mirror = bool(getattr(immutable_log, "require_mirror", False))

    for entry in entries:
        current = dict(entry)
        sequence_num = current.get("sequence_num")
        prev_event_digest = current.get("prev_event_digest")
        prev_lookup_hash = current.get("prev_lookup_hash")
        public_history_status = _classify_public_history_status(current)

        if public_history_status is not None:
            current["public_history_ok"] = False
            current["public_history_status"] = public_history_status
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_ok"] = False
            current["predecessor_status"] = "unsupported"
            if public_history_status == "cache-assisted":
                current.setdefault("errors", []).append(
                    "Historical replay facts came from process-local cache rather than Rekor-auditable materialization"
                )
            elif public_history_status == "baseline-missing":
                current.setdefault("errors", []).append(
                    "Event Log 0 baseline facts were not recoverable from Rekor-auditable replay material"
                )
            else:
                current.setdefault("errors", []).append(
                    "Verifier-critical historical replay facts were not materialized from public Rekor entry data"
                )
            annotated.append(current)
            continue

        current["public_history_ok"] = True
        current["public_history_status"] = "public"
        current.setdefault(
            "history_materialization_provenance",
            current.get("replay_provenance") if current.get("replay_provenance") in {"attestation-storage", "mirror"} else "public",
        )

        if sequence_num == 1 and prev_event_digest is None and prev_lookup_hash is None:
            current["predecessor_ok"] = True
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "origin"
            annotated.append(current)
            continue

        if not isinstance(sequence_num, int) or sequence_num < 1:
            current["predecessor_ok"] = None
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unverifiable"
            current.setdefault("errors", []).append("Replay entry is missing a valid sequence_num")
            annotated.append(current)
            continue

        if prev_event_digest is None and prev_lookup_hash is None:
            boundary_status = _classify_replay_boundary(current, entries)
            current["candidate_count"] = 0
            current["materialized_candidate_count"] = 0
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unverifiable"
            if boundary_status is not None:
                current["boundary_status"] = boundary_status
                current["predecessor_ok"] = False if boundary_status == "invalid" else None
                if boundary_status == "invalid":
                    current.setdefault("errors", []).append(
                        "Signed predecessor contract regressed after reservation-backed replay began"
                    )
                else:
                    current.setdefault("errors", []).append(
                        "Signed predecessor contract unavailable at legacy-to-reservation replay boundary"
                    )
            else:
                current["predecessor_ok"] = None
            annotated.append(current)
            continue

        candidates, lookup_error = _materialize_predecessor_candidates(current, entries, immutable_log)
        current["candidate_count"] = len(candidates)
        current["materialized_candidate_count"] = len(candidates)

        if lookup_error is not None:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "lookup_failed"
            current.setdefault("errors", []).append(f"Predecessor candidate lookup failed: {lookup_error}")
            annotated.append(current)
            continue

        if current["candidate_count"] == 0:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "missing"
            current.setdefault("errors", []).append("Missing predecessor entry for signed replay contract")
            annotated.append(current)
            continue

        materialized_candidates = [
            candidate
            for candidate in candidates
            if candidate.get("sequence_num") is not None
            and candidate.get("digest") is not None
            and candidate.get("payload_hash") is not None
        ]
        current["materialized_candidate_count"] = len(materialized_candidates)
        if current.get("sequence_num") == 3:
            logger.info(
                "replay_predecessor_decision=%s",
                canonical_json(
                    {
                        "chain_id": current.get("chain_id"),
                        "current_event_id": current.get("event_id"),
                        "current_sequence_num": current.get("sequence_num"),
                        "prev_lookup_hash": current.get("prev_lookup_hash"),
                        "candidate_count": len(candidates),
                        "materialized_candidate_count": len(materialized_candidates),
                        "candidate_summaries": [
                            _summarize_normalized_candidate(candidate) for candidate in candidates
                        ],
                        "materialized_candidate_summaries": [
                            _summarize_normalized_candidate(candidate) for candidate in materialized_candidates
                        ],
                    }
                ),
            )
        if materialized_candidates and len(materialized_candidates) != len(candidates):
            current.setdefault("errors", []).append(
                "Some predecessor candidates could not be normalized into replayable entries"
            )
        if not materialized_candidates:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "decode_failed"
            candidate_errors = [
                error
                for candidate in candidates
                for error in (candidate.get("errors") or [])
                if isinstance(error, str)
            ]
            if candidate_errors:
                current.setdefault("errors", []).extend(candidate_errors)
            current.setdefault("errors", []).append(
                "Discovered predecessor candidates could not be normalized into replayable entries"
            )
            annotated.append(current)
            continue

        public_candidates = [
            candidate
            for candidate in materialized_candidates
            if _classify_public_history_status(candidate) is None
        ]
        mirrored_candidates = [
            candidate for candidate in public_candidates if candidate.get("replay_provenance") == "mirror"
        ]
        if require_mirror and not mirrored_candidates:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unsupported"
            current.setdefault("errors", []).append(
                "Mirror-required policy could not resolve mirrored predecessor material for the signed lookup hash"
            )
            annotated.append(current)
            continue
        if not public_candidates:
            current["predecessor_ok"] = False
            current["matched_candidate_count"] = 0
            current["predecessor_status"] = "unsupported"
            current.setdefault("errors", []).append(
                "Predecessor proof depended on cache-assisted or otherwise non-public candidate materialization"
            )
            annotated.append(current)
            continue

        matches = [
            candidate
            for candidate in public_candidates
            if current.get("chain_id") == candidate.get("chain_id")
            and sequence_num == candidate.get("sequence_num", 0) + 1
            and prev_event_digest == candidate.get("digest")
            and prev_lookup_hash == candidate.get("payload_hash")
        ]
        current["matched_candidate_count"] = len(matches)
        if len(matches) == 1:
            current["predecessor_ok"] = True
            current["predecessor_status"] = "proven"
            current["history_materialization_provenance"] = matches[0].get("replay_provenance", "public")
        elif len(matches) > 1:
            mirror_matches = [candidate for candidate in matches if candidate.get("replay_provenance") == "mirror"]
            equivalent_contracts = {_matched_predecessor_contract(candidate) for candidate in matches}
            if mirror_matches and len(equivalent_contracts) == 1:
                current["predecessor_ok"] = True
                current["predecessor_status"] = "proven"
                current["history_materialization_provenance"] = "mirror"
            else:
                current["predecessor_ok"] = False
                current["predecessor_status"] = "ambiguous"
                current.setdefault("errors", []).append(
                    "Multiple predecessor candidates matched the signed replay contract"
                )
        else:
            current["predecessor_ok"] = False
            current["predecessor_status"] = "missing"
            current.setdefault("errors", []).append(
                "Signed predecessor contract did not match the replayed predecessor entry"
            )
        annotated.append(current)

    return annotated
__all__ = ['_decode_rekor_body', '_decode_dsse_payload', '_extract_committed_payload_hash', '_decode_attestation_payload', '_normalize_verification_entry', '_annotate_owner_verification', '_annotate_delegation_verification', '_entry_matches_chain', '_classify_public_history_status', '_candidate_identity', '_summarize_replay_candidate', '_summarize_normalized_candidate', '_candidate_quality', '_matched_predecessor_contract', '_has_signed_predecessor_contract', '_classify_replay_boundary', '_materialize_predecessor_candidates', '_annotate_predecessor_verification', '_extract_signer_identity']

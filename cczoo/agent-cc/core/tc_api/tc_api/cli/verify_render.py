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

from typing import Any, Dict

from .verify_replay import summarize_replay_rollout


def render_text(result: Dict[str, Any]) -> str:
    attested_head = result.get("attested_head") or {}
    replay = result.get("replay") or {}
    fallback = result.get("fallback") or {}
    log_verification = result.get("log_verification") or {}
    lines = [
        f"Chain: {result['target']['chain_id']}",
        f"Status: {result['summary']['status']}",
        f"Verification tier: {result['summary'].get('verification_tier')}",
        f"Mode: {result['mode']['input_mode']} -> {result['mode']['verification_mode']} ({result['mode']['status_detail']})",
        f"Entries: {result['summary']['entry_count']} total, {result['summary']['confirmed_count']} confirmed, {result['summary']['pending_count']} pending",
        "Replay:",
        f"  immutable_backend: reachable={replay.get('reachable')} success={replay.get('success')} head_log_id={replay.get('head_log_id')}",
    ]
    rollout_status, rollout_detail = summarize_replay_rollout(replay.get("entries", []))
    provenance = replay.get("provenance") or {"status": "unavailable", "detail": "no replay provenance summary available"}
    lines.append(f"  rollout={rollout_status} {rollout_detail}")
    lines.append(f"  provenance={provenance.get('status')} {provenance.get('detail')}")
    if result["mode"].get("input_mode") == "quote-backed":
        lines.append("  trust_sources=public_replay(history, baseline) + direct_quote(current_head_binding)")
    else:
        lines.append("  trust_sources=public_replay(history, baseline) + exported_evidence(current_head_binding)")

    lines.append("Head log verification:")
    lines.append(
        "  "
        f"status={log_verification.get('status')} inclusion={log_verification.get('inclusion_status')} "
        f"checkpoint={log_verification.get('checkpoint_status')} scope={log_verification.get('scope')}"
    )
    bootstrap_trust = log_verification.get("bootstrap_trust") or {}
    if log_verification.get("log_id") is not None:
        lines.append(
            "  "
            f"log_id={log_verification.get('log_id')} entry_uuid={log_verification.get('entry_uuid')} "
            f"log_index={log_verification.get('log_index')}"
        )
    if bootstrap_trust:
        lines.append(
            "  "
            f"bootstrap_trust_configured={bootstrap_trust.get('configured')} source={bootstrap_trust.get('source')} "
            f"historical_consistency_proven={bootstrap_trust.get('consistency_proven')}"
        )
    for limitation in log_verification.get("limitations", []):
        lines.append(f"  limitation: {limitation}")
    for reason in log_verification.get("reasons", []):
        lines.append(f"  reason: {reason}")

    if attested_head.get("present"):
        lines.append("Attested head:")
        lines.append(
            "  "
            f"valid={attested_head.get('valid')} matches_replay={attested_head.get('matches_replay')} "
            f"freshness={attested_head.get('freshness')}"
        )
        quote_parse = attested_head.get("quote_parse") or {}
        if quote_parse.get("present"):
            lines.append(
                "  "
                f"quote_parsed={quote_parse.get('parsed')} report_data_match={quote_parse.get('report_data_prefix_matches_binding')} "
                f"rtmr{quote_parse.get('mr_index')}_match={quote_parse.get('mr_value_matches_quote')}"
            )
        if attested_head.get("contract_scope"):
            lines.append(f"  contract_scope={attested_head.get('contract_scope')}")
    elif result["mode"].get("fallback_used"):
        lines.append("Attested head:")
        lines.append("  not used (explicit live troubleshooting mode)")

    if result["mode"].get("fallback_used"):
        lines.append("Troubleshooting:")
        lines.append(
            "  "
            f"reachable={fallback.get('reachable')} valid={fallback.get('valid')} rtmr_available={fallback.get('rtmr_available')}"
        )

    diagnostics = result.get("diagnostics") or {}
    replay_diagnostics = diagnostics.get("replay") or {}
    first_entry_issue = replay_diagnostics.get("first_entry_issue")
    event_log0_audit = replay_diagnostics.get("event_log0_audit") or {}
    if diagnostics:
        lines.append("Diagnostics:")
        lines.append(
            "  "
            f"replay_success={replay_diagnostics.get('success')} provenance_status={replay_diagnostics.get('provenance_status')} "
            f"fallback_valid={(diagnostics.get('fallback') or {}).get('valid')} first_error={diagnostics.get('first_error')}"
        )
        if event_log0_audit.get("present"):
            lines.append(
                "  "
                f"event_log0_audit=event_id={event_log0_audit.get('event_id')} "
                f"ccel_eventlog_b64_present={event_log0_audit.get('ccel_eventlog_b64_present')} "
                f"ccel_eventlog_b64_chars={event_log0_audit.get('ccel_eventlog_b64_chars')} "
                f"ccel_eventlog_decodable={event_log0_audit.get('ccel_eventlog_decodable')} "
                f"ccel_eventlog_bytes={event_log0_audit.get('ccel_eventlog_bytes')}"
            )
        if first_entry_issue is not None:
            lines.append(
                "  "
                f"first_entry_issue=index={first_entry_issue.get('index')} seq={first_entry_issue.get('sequence_num')} "
                f"event_id={first_entry_issue.get('event_id')} predecessor_status={first_entry_issue.get('predecessor_status')} "
                f"public_history_status={first_entry_issue.get('public_history_status')} boundary_status={first_entry_issue.get('boundary_status')}"
            )
        fallback_issue = (diagnostics.get("fallback") or {}).get("first_entry_issue")
        if fallback_issue is not None:
            lines.append(
                "  "
                f"fallback_first_entry_issue=seq={fallback_issue.get('seq')} event_id={fallback_issue.get('event_id')} "
                f"owner_ok={fallback_issue.get('owner_ok')} owner_status={fallback_issue.get('owner_status')} "
                f"predecessor_status={fallback_issue.get('predecessor_status')}"
            )

    lines.append("Per-record replay detail:")

    for entry in replay.get("entries", []):
        diagnostic_bits = [
            f"predecessor_ok={entry.get('predecessor_ok')}",
            f"predecessor_status={entry.get('predecessor_status')}",
            f"candidate_count={entry.get('candidate_count')}",
            f"materialized_candidate_count={entry.get('materialized_candidate_count')}",
            f"matched_candidate_count={entry.get('matched_candidate_count')}",
        ]
        if entry.get("boundary_status") is not None:
            diagnostic_bits.append(f"boundary_status={entry.get('boundary_status')}")
        if entry.get("public_history_status") is not None:
            diagnostic_bits.append(f"public_history_status={entry.get('public_history_status')}")
        if entry.get("replay_provenance") is not None:
            diagnostic_bits.append(f"replay_provenance={entry.get('replay_provenance')}")
        if entry.get("history_materialization_provenance") is not None:
            diagnostic_bits.append(
                f"history_materialization_provenance={entry.get('history_materialization_provenance')}"
            )
        lines.append(
            "  - "
            f"index={entry.get('index')} seq={entry.get('sequence_num')} event_id={entry.get('event_id')} "
            f"event_type={entry.get('event_type')} digest={entry.get('digest')} "
            + " ".join(diagnostic_bits)
        )

    if result["mode"].get("fallback_used") and fallback.get("entries"):
        lines.append("Fallback per-record detail:")
        for entry in fallback.get("entries", []):
            diagnostic_bits = [
                f"predecessor_status={entry.get('predecessor_status')}",
                f"owner_ok={entry.get('owner_ok')}",
                f"owner_status={entry.get('owner_status')}",
            ]
            lines.append(
                "  - "
                f"seq={entry.get('seq')} event_id={entry.get('event_id')} record_id={entry.get('record_id')} "
                + " ".join(diagnostic_bits)
            )

    profiles = result.get("profiles") or {}
    if profiles:
        lines.append("Profiles:")
        for profile_name, profile_result in profiles.items():
            lines.append(
                f"  - {profile_name}: status={profile_result.get('status')} matched={len(profile_result.get('matched_event_ids', []))}"
            )
            if profile_result.get("target_launch_id"):
                lines.append(f"    launch_id={profile_result.get('target_launch_id')}")
            for warning in profile_result.get("warnings", []):
                lines.append(f"    warning: {warning}")
            for error in profile_result.get("errors", []):
                lines.append(f"    error: {error}")

    if result["errors"]:
        lines.append("Errors:")
        for error in result["errors"]:
            lines.append(f"  - {error}")

    return "\n".join(lines)

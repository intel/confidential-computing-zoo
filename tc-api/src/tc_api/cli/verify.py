import argparse
import base64
import hashlib
import json
import struct
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tc_api.config import TRUCON_SERVICE_TOKEN, TRUCON_URL
from tc_api.tlog_client import TrustedLogAPI
from tlog_rekor.adapter import SigstoreLogAdapter
from tc_api.trucon.evidence import (
    compute_binding_expected_value,
    decode_binding_expected_value,
    load_attested_head_evidence_json,
)
from tc_api.verification_profiles import evaluate_profiles


_TDX_QUOTE_HEADER_SIZE = 48
_TDX_QUOTE_V4_BODY_SIZE = 584
_TDX_QUOTE_V5_DESCRIPTOR_SIZE = 6
_TDX_QUOTE_REPORT_DATA_START = 0x208
_TDX_QUOTE_REPORT_DATA_END = 0x248
_TDX_QUOTE_RTMR_START = 0x148
_TDX_QUOTE_RTMR_COUNT = 4
_TDX_QUOTE_RTMR_SIZE = 48
_TDX_QUOTE_SUPPORTED_VERSIONS = {4, 5}


def _parse_tdx_quote(quote_b64: str) -> Dict[str, Any]:
    try:
        quote_bytes = base64.b64decode(quote_b64, validate=True)
    except Exception as exc:
        raise ValueError(f"quote was not valid base64: {exc}") from exc

    if len(quote_bytes) < _TDX_QUOTE_HEADER_SIZE:
        raise ValueError("quote was shorter than the TDX quote header")

    version = struct.unpack_from("<H", quote_bytes, 0)[0]
    if version not in _TDX_QUOTE_SUPPORTED_VERSIONS:
        raise ValueError(f"unsupported TDX quote version: {version}")

    body_type: Optional[int] = None
    body_size: int
    body: bytes
    if version == 4:
        body_size = _TDX_QUOTE_V4_BODY_SIZE
        required_size = _TDX_QUOTE_HEADER_SIZE + body_size
        if len(quote_bytes) < required_size:
            raise ValueError(
                f"quote version 4 was truncated: expected at least {required_size} bytes, got {len(quote_bytes)}"
            )
        body = quote_bytes[_TDX_QUOTE_HEADER_SIZE:required_size]
    else:
        descriptor_end = _TDX_QUOTE_HEADER_SIZE + _TDX_QUOTE_V5_DESCRIPTOR_SIZE
        if len(quote_bytes) < descriptor_end:
            raise ValueError("quote version 5 was truncated before the body descriptor")
        body_type = struct.unpack_from("<H", quote_bytes, _TDX_QUOTE_HEADER_SIZE)[0]
        body_size = struct.unpack_from("<I", quote_bytes, _TDX_QUOTE_HEADER_SIZE + 2)[0]
        if body_size < _TDX_QUOTE_REPORT_DATA_END:
            raise ValueError(f"quote version 5 body was too small to contain report data: {body_size} bytes")
        required_size = descriptor_end + body_size
        if len(quote_bytes) < required_size:
            raise ValueError(
                f"quote version 5 was truncated: expected at least {required_size} bytes, got {len(quote_bytes)}"
            )
        body = quote_bytes[descriptor_end:required_size]

    report_data = body[_TDX_QUOTE_REPORT_DATA_START:_TDX_QUOTE_REPORT_DATA_END]
    if len(report_data) != 64:
        raise ValueError(f"quote report_data had unexpected size: {len(report_data)}")

    rtmrs = []
    for index in range(_TDX_QUOTE_RTMR_COUNT):
        start = _TDX_QUOTE_RTMR_START + (index * _TDX_QUOTE_RTMR_SIZE)
        end = start + _TDX_QUOTE_RTMR_SIZE
        rtmr = body[start:end]
        if len(rtmr) != _TDX_QUOTE_RTMR_SIZE:
            raise ValueError(f"quote RTMR[{index}] had unexpected size: {len(rtmr)}")
        rtmrs.append(rtmr.hex())

    return {
        "parsed": True,
        "version": version,
        "body_type": body_type,
        "body_size": body_size,
        "quote_size": len(quote_bytes),
        "report_data_hex": report_data.hex(),
        "rtmrs": rtmrs,
    }


def _inspect_evidence_quote(evidence: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "present": bool(evidence.quote),
        "parsed": False,
        "version": None,
        "body_type": None,
        "body_size": None,
        "quote_size": None,
        "report_data_hex": None,
        "report_data_prefix_hex": None,
        "report_data_prefix_matches_binding": None,
        "report_data_zero_padded": None,
        "rtmrs": [],
        "mr_index": 2,
        "mr_value_matches_quote": None,
        "errors": [],
    }
    if not evidence.quote:
        return result

    try:
        parsed = _parse_tdx_quote(evidence.quote)
    except Exception as exc:
        result["errors"].append(f"Quote parsing failed: {exc}")
        return result

    result.update(parsed)
    result["parsed"] = True

    report_data_hex = parsed["report_data_hex"]
    expected_value = evidence.report_data_binding.expected_value
    if not isinstance(expected_value, str) or not expected_value.startswith("sha384:"):
        result["errors"].append("Evidence expected_value did not use the supported sha384: format")
        return result

    expected_prefix_hex = expected_value.removeprefix("sha384:").lower()
    report_prefix_hex = report_data_hex[: len(expected_prefix_hex)]
    report_padding_hex = report_data_hex[len(expected_prefix_hex):]
    result["report_data_prefix_hex"] = report_prefix_hex
    result["report_data_prefix_matches_binding"] = report_prefix_hex == expected_prefix_hex
    result["report_data_zero_padded"] = set(report_padding_hex) <= {"0"}
    if result["report_data_prefix_matches_binding"] is False:
        result["errors"].append("Quote REPORTDATA prefix did not match evidence report_data_binding.expected_value")
    if result["report_data_zero_padded"] is False:
        result["errors"].append("Quote REPORTDATA suffix was not zero-padded after the bound sha384 digest")

    quote_mr_value = None
    if len(parsed["rtmrs"]) > result["mr_index"]:
        quote_mr_value = parsed["rtmrs"][result["mr_index"]]
    result["quote_mr_value"] = quote_mr_value
    result["mr_value_matches_quote"] = quote_mr_value == evidence.mr_value
    if result["mr_value_matches_quote"] is False:
        result["errors"].append(
            f"Quote RTMR[{result['mr_index']}] did not match evidence mr_value"
        )
    return result


def _fetch_trucon_json(path: str) -> Dict[str, Any]:
    url = f"{TRUCON_URL.rstrip('/')}{path}"
    request = urllib.request.Request(url, method="GET")
    if TRUCON_SERVICE_TOKEN:
        request.add_header("Authorization", f"Bearer {TRUCON_SERVICE_TOKEN}")

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a trusted-log chain using exported evidence, direct quote input, or explicit live troubleshooting mode"
    )
    parser.add_argument("chain_id", nargs="?", help="Chain identifier to inspect in explicit live troubleshooting mode")
    parser.add_argument(
        "--evidence",
        dest="evidence_path",
        help="Path to exported attested-head evidence JSON, or '-' to read from stdin",
    )
    parser.add_argument(
        "--quote",
        dest="quote_value",
        help="Base64-encoded quote value, '@path' to read a file, or '-' to read from stdin",
    )
    parser.add_argument(
        "--head-log-id",
        dest="head_log_id",
        help="Immutable log head to replay when using --quote",
    )
    parser.add_argument(
        "--troubleshoot-live",
        action="store_true",
        dest="troubleshoot_live",
        help="Use live TruCon APIs as an internal troubleshooting path instead of supported external verification",
    )
    parser.add_argument("--signer-identity", dest="signer_identity")
    parser.add_argument("--expected-entry-count", type=int, dest="expected_entry_count")
    parser.add_argument("--fail-on-pending", action="store_true")
    parser.add_argument("--require-tee", action="store_true")
    parser.add_argument("--mirror-dir", dest="mirror_dir")
    parser.add_argument("--require-mirror", action="store_true", dest="require_mirror")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _normalize_replay_entries(immutable_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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


def _build_diagnostics(result: Dict[str, Any]) -> Dict[str, Any]:
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
            "event_log0_audit": _collect_event_log0_audit(replay_entries),
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


def _attach_profile_results(result: Dict[str, Any]) -> Dict[str, Any]:
    replay_entries = result.get("entries", [])
    profiles = evaluate_profiles(replay_entries)
    result["profiles"] = profiles
    result["diagnostics"] = _build_diagnostics(result)
    return result


def _summarize_replay_rollout(entries: List[Dict[str, Any]]) -> tuple[str, str]:
    boundary_statuses = [entry.get("boundary_status") for entry in entries if entry.get("boundary_status")]
    if "invalid" in boundary_statuses:
        return "invalid", "reservation-backed replay regressed to incompatible legacy linkage"
    if "degraded" in boundary_statuses:
        return "degraded", "mixed-regime migration state; replay visibility exists but continuous reservation-backed predecessor proof is unavailable across the full history"
    return "supported", "continuous reservation-backed predecessor proof is available for the replayed history"


def _summarize_replay_provenance(entries: List[Dict[str, Any]]) -> tuple[str, str]:
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


def _compute_verification_tier(provenance_status: str, attested_valid: bool) -> str:
    if provenance_status == "mirrored" and attested_valid:
        return "public+mirrored+attested"
    if provenance_status == "mirrored":
        return "public+mirrored"
    if provenance_status == "attestation-storage":
        return "public+attestation-storage"
    return "public-only"


def _entry_value(predicate_entries: List[Dict[str, Any]], key: str) -> Optional[str]:
    for entry in predicate_entries:
        if isinstance(entry, dict) and entry.get("key") == key:
            value = entry.get("value")
            return value if isinstance(value, str) else None
    return None


def _collect_event_log0_audit(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    ccel_eventlog_b64 = _entry_value(predicate_entries, "ccel_eventlog_b64")
    audit.update(
        {
            "present": baseline_entry.get("event_type") == "chain.init",
            "event_id": baseline_entry.get("event_id"),
            "chain_id": baseline_entry.get("chain_id"),
            "baseline_rtmr": _entry_value(predicate_entries, "baseline_rtmr"),
            "ccel_digest": _entry_value(predicate_entries, "ccel_digest"),
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


def _derive_replay_chain_state(immutable_result: Dict[str, Any]) -> Dict[str, Any]:
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

    baseline_rtmr = _entry_value(baseline_entries, "baseline_rtmr")
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


def _format_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _load_evidence(args: argparse.Namespace) -> Any:
    if not args.evidence_path:
        return None

    if args.evidence_path == "-":
        payload = sys.stdin.read()
        source = "stdin"
    else:
        source = args.evidence_path
        payload = Path(args.evidence_path).read_text(encoding="utf-8")

    evidence = load_attested_head_evidence_json(payload)
    if args.chain_id and args.chain_id != evidence.chain_id:
        raise ValueError(
            f"Provided chain_id '{args.chain_id}' does not match evidence chain_id '{evidence.chain_id}'"
        )
    expected_value = compute_binding_expected_value(
        chain_id=evidence.chain_id,
        sequence_num=evidence.sequence_num,
        head_log_id=evidence.head_log_id,
        mr_value=evidence.mr_value,
    )
    if evidence.report_data_binding.expected_value != expected_value:
        raise ValueError(
            "Evidence report_data_binding.expected_value did not match canonical recomputation"
        )
    evidence.__dict__["_source"] = source
    evidence.__dict__["_recomputed_expected_value"] = expected_value
    return evidence


def _load_quote_value(args: argparse.Namespace) -> Optional[Dict[str, str]]:
    if not args.quote_value:
        return None

    if args.quote_value == "-":
        source = "stdin"
        payload = sys.stdin.read()
    elif args.quote_value.startswith("@"):
        source = args.quote_value[1:]
        payload = Path(source).read_text(encoding="utf-8")
    else:
        source = "argument"
        payload = args.quote_value

    quote_value = payload.strip()
    if not quote_value:
        raise ValueError("Quote input was empty")

    return {"quote": quote_value, "source": source}


def _inspect_quote_binding(
    quote_b64: str,
    expected_value: str,
    expected_mr_value: Optional[str],
    expected_mr_label: str,
) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "present": bool(quote_b64),
        "parsed": False,
        "version": None,
        "body_type": None,
        "body_size": None,
        "quote_size": None,
        "report_data_hex": None,
        "report_data_prefix_hex": None,
        "report_data_prefix_matches_binding": None,
        "report_data_zero_padded": None,
        "rtmrs": [],
        "mr_index": 2,
        "mr_value_matches_quote": None,
        "errors": [],
    }
    if not quote_b64:
        return result

    try:
        parsed = _parse_tdx_quote(quote_b64)
    except Exception as exc:
        result["errors"].append(f"Quote parsing failed: {exc}")
        return result

    result.update(parsed)
    result["parsed"] = True

    try:
        expected_bytes = decode_binding_expected_value(expected_value)
    except ValueError as exc:
        result["errors"].append(str(exc))
        return result

    report_data_hex = parsed["report_data_hex"]
    expected_prefix_hex = expected_bytes.hex()
    report_prefix_hex = report_data_hex[: len(expected_prefix_hex)]
    report_padding_hex = report_data_hex[len(expected_prefix_hex):]
    result["report_data_prefix_hex"] = report_prefix_hex
    result["report_data_prefix_matches_binding"] = report_prefix_hex == expected_prefix_hex
    result["report_data_zero_padded"] = set(report_padding_hex) <= {"0"}
    if result["report_data_prefix_matches_binding"] is False:
        result["errors"].append("Quote REPORTDATA prefix did not match the expected head_log_id binding bytes")
    if result["report_data_zero_padded"] is False:
        result["errors"].append("Quote REPORTDATA suffix was not zero-padded after the bound head_log_id bytes")

    quote_mr_value = None
    if len(parsed["rtmrs"]) > result["mr_index"]:
        quote_mr_value = parsed["rtmrs"][result["mr_index"]]
    result["quote_mr_value"] = quote_mr_value
    result["mr_value_matches_quote"] = quote_mr_value == expected_mr_value
    if expected_mr_value is None:
        result["mr_value_matches_quote"] = None
    elif result["mr_value_matches_quote"] is False:
        result["errors"].append(
            f"Quote RTMR[{result['mr_index']}] did not match {expected_mr_label}"
        )
    return result


def _run_fallback_verification(args: argparse.Namespace, chain_id: str) -> Dict[str, Any]:
    trucon_result: Dict[str, Any] = {"reachable": False, "data": None, "error": None}
    chain_state: Dict[str, Any] = {}
    try:
        chain_state = _fetch_trucon_json(f"/chain-state/{chain_id}")
    except urllib.error.HTTPError as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: HTTP {exc.code}"
    except Exception as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: {exc}"

    try:
        trucon_result["data"] = _fetch_trucon_json(f"/verify-chain/{chain_id}")
        trucon_result["reachable"] = True
    except urllib.error.HTTPError as exc:
        trucon_result["error"] = f"TruCon verification failed: HTTP {exc.code}"
    except Exception as exc:
        trucon_result["error"] = f"TruCon verification failed: {exc}"

    return {"chain_state": chain_state, "trucon": trucon_result}


def _load_immutable_result(args: argparse.Namespace, chain_id: str, head_log_id: Optional[str]) -> Dict[str, Any]:
    if head_log_id:
        tlog = TrustedLogAPI(
            immutable_log=SigstoreLogAdapter(bundle_mirror_dir=args.mirror_dir),
            trucon_url=TRUCON_URL,
        )
        result = tlog.verify_record(
            head_log_id,
            policy={
                "chain_id": chain_id,
                "signer_identity": args.signer_identity,
                "expected_entry_count": args.expected_entry_count,
                "require_mirror": args.require_mirror,
            },
        )
        return {
            "reachable": True,
            "success": result.success,
            "errors": result.errors,
            "details": result.details,
            "head_log_id": head_log_id,
        }

    return {
        "reachable": False,
        "success": False,
        "errors": [f"No confirmed immutable log head for chain '{chain_id}'"],
        "details": {
            "source": "immutable_backend",
            "entry_count": 0,
            "entries": [],
            "subject": f"trusted-log-chain_{chain_id}",
            "chain_id": chain_id,
        },
        "head_log_id": None,
    }


def _normalize_evidence_result(
    args: argparse.Namespace,
    evidence: Any,
    immutable_result: Dict[str, Any],
) -> Dict[str, Any]:
    immutable_data = immutable_result.get("details") or {}
    replay_entries = _normalize_replay_entries(immutable_data.get("entries", []))
    derived_replay = _derive_replay_chain_state(immutable_result)
    quote_parse = _inspect_quote_binding(
        evidence.quote,
        evidence.report_data_binding.expected_value,
        evidence.mr_value,
        "evidence mr_value",
    )
    attested_errors: List[str] = []
    mismatches: List[str] = []

    if derived_replay.get("chain_id") != evidence.chain_id:
        mismatches.append(
            f"chain_id mismatch: replay={derived_replay.get('chain_id')} evidence={evidence.chain_id}"
        )
    if derived_replay.get("sequence_num") != evidence.sequence_num:
        mismatches.append(
            f"sequence_num mismatch: replay={derived_replay.get('sequence_num')} evidence={evidence.sequence_num}"
        )
    if immutable_result.get("head_log_id") != evidence.head_log_id:
        mismatches.append(
            f"head_log_id mismatch: replay={immutable_result.get('head_log_id')} evidence={evidence.head_log_id}"
        )
    if derived_replay.get("mr_value") != evidence.mr_value:
        mismatches.append(
            f"mr_value mismatch: replay={derived_replay.get('mr_value')} evidence={evidence.mr_value}"
        )
    if evidence.head_event_digest and derived_replay.get("head_event_digest") != evidence.head_event_digest:
        mismatches.append(
            "head_event_digest mismatch: replay="
            f"{derived_replay.get('head_event_digest')} evidence={evidence.head_event_digest}"
        )

    attested_errors.extend(derived_replay.get("errors", []))
    attested_errors.extend(mismatches)
    attested_errors.extend(quote_parse.get("errors", []))

    expired = False
    if evidence.expires_at is not None:
        expired = evidence.expires_at < datetime.now(timezone.utc)
        if expired:
            attested_errors.append("Evidence package has expired")

    if args.require_tee and evidence.quote:
        tee_error = None
    elif args.require_tee:
        tee_error = "TEE evidence was required but unavailable"
        attested_errors.append(tee_error)
    else:
        tee_error = None

    errors: List[str] = []
    errors.extend(immutable_result.get("errors", []))
    errors.extend(attested_errors)

    immutable_success = immutable_result.get("success", False)
    attested_valid = not attested_errors
    success = immutable_success and attested_valid
    status = "verified" if success else "failed"
    provenance_status, provenance_detail = _summarize_replay_provenance(replay_entries)
    verification_tier = _compute_verification_tier(provenance_status, attested_valid)

    result = {
        "target": {
            "chain_id": evidence.chain_id,
            "head_log_id": evidence.head_log_id,
            "source": "evidence-package",
        },
        "mode": {
            "input_mode": "evidence-backed",
            "tee_required": args.require_tee,
            "tee_available": True,
            "verification_mode": "evidence-backed",
            "status_detail": "tee-attested",
            "fallback_used": False,
            "mirror_required": args.require_mirror,
            "mirror_configured": bool(args.mirror_dir),
        },
        "summary": {
            "success": success,
            "status": status,
            "verification_tier": verification_tier,
            "entry_count": immutable_data.get("entry_count", 0),
            "confirmed_count": immutable_data.get("entry_count", 0),
            "pending_count": 0,
            "first_error_at": None,
        },
        "replay": {
            "reachable": immutable_result.get("reachable", False),
            "success": immutable_success,
            "head_log_id": immutable_result.get("head_log_id"),
            "entry_count": immutable_data.get("entry_count", 0),
            "subject": immutable_data.get("subject"),
            "entries": replay_entries,
            "derived": derived_replay,
            "provenance": {
                "status": provenance_status,
                "detail": provenance_detail,
            },
        },
        "attested_head": {
            "present": True,
            "valid": attested_valid,
            "tee_type": evidence.tee_type,
            "source": evidence.__dict__.get("_source"),
            "generated_at": _format_timestamp(evidence.generated_at),
            "expires_at": _format_timestamp(evidence.expires_at),
            "expired": expired,
            "freshness": "expired" if expired else ("bounded" if evidence.expires_at else "no-expiry-bound"),
            "binding_verified": evidence.report_data_binding.expected_value == evidence.__dict__.get("_recomputed_expected_value"),
            "expected_value": evidence.report_data_binding.expected_value,
            "recomputed_expected_value": evidence.__dict__.get("_recomputed_expected_value"),
            "matches_replay": not mismatches and not derived_replay.get("errors"),
            "mismatches": mismatches,
            "quote_parse": quote_parse,
            "head_log_id": evidence.head_log_id,
            "sequence_num": evidence.sequence_num,
            "mr_value": evidence.mr_value,
            "head_event_digest": evidence.head_event_digest,
            "errors": attested_errors,
            "contract_scope": "current-head binding only",
        },
        "fallback": None,
        "sources": {
            "immutable_backend": {
                "reachable": immutable_result.get("reachable", False),
                "success": immutable_success,
                "head_log_id": immutable_result.get("head_log_id"),
                "entry_count": immutable_data.get("entry_count", 0),
                "subject": immutable_data.get("subject"),
            },
            "trucon_chain": None,
        },
        "entries": replay_entries,
        "errors": errors,
    }
    if tee_error and tee_error not in result["errors"]:
        result["errors"].append(tee_error)
    return _attach_profile_results(result)


def _normalize_quote_result(
    args: argparse.Namespace,
    quote_input: Dict[str, str],
    immutable_result: Dict[str, Any],
) -> Dict[str, Any]:
    immutable_data = immutable_result.get("details") or {}
    replay_entries = _normalize_replay_entries(immutable_data.get("entries", []))
    derived_replay = _derive_replay_chain_state(immutable_result)
    expected_value = None
    if not derived_replay.get("errors"):
        expected_value = compute_binding_expected_value(
            chain_id=args.chain_id,
            sequence_num=derived_replay.get("sequence_num"),
            head_log_id=args.head_log_id,
            mr_value=derived_replay.get("mr_value"),
        )
    quote_parse = _inspect_quote_binding(
        quote_input["quote"],
        expected_value or "",
        derived_replay.get("mr_value"),
        "replay-derived mr_value",
    )

    attested_errors: List[str] = []
    attested_errors.extend(derived_replay.get("errors", []))
    attested_errors.extend(quote_parse.get("errors", []))

    errors: List[str] = []
    errors.extend(immutable_result.get("errors", []))
    errors.extend(attested_errors)

    immutable_success = immutable_result.get("success", False)
    attested_valid = not attested_errors
    success = immutable_success and attested_valid
    status = "verified" if success else "failed"
    provenance_status, provenance_detail = _summarize_replay_provenance(replay_entries)
    verification_tier = _compute_verification_tier(provenance_status, attested_valid)

    return _attach_profile_results({
        "target": {
            "chain_id": args.chain_id,
            "head_log_id": args.head_log_id,
            "source": "direct-quote",
        },
        "mode": {
            "input_mode": "quote-backed",
            "tee_required": True,
            "tee_available": True,
            "verification_mode": "quote-backed",
            "status_detail": "tee-attested",
            "fallback_used": False,
            "mirror_required": args.require_mirror,
            "mirror_configured": bool(args.mirror_dir),
        },
        "summary": {
            "success": success,
            "status": status,
            "verification_tier": verification_tier,
            "entry_count": immutable_data.get("entry_count", 0),
            "confirmed_count": immutable_data.get("entry_count", 0),
            "pending_count": 0,
            "first_error_at": None,
        },
        "replay": {
            "reachable": immutable_result.get("reachable", False),
            "success": immutable_success,
            "head_log_id": immutable_result.get("head_log_id"),
            "entry_count": immutable_data.get("entry_count", 0),
            "subject": immutable_data.get("subject"),
            "entries": replay_entries,
            "derived": derived_replay,
            "provenance": {
                "status": provenance_status,
                "detail": provenance_detail,
            },
        },
        "attested_head": {
            "present": True,
            "valid": attested_valid,
            "tee_type": "tdx",
            "source": quote_input["source"],
            "generated_at": None,
            "expires_at": None,
            "expired": False,
            "freshness": "no-expiry-bound",
            "binding_verified": quote_parse.get("report_data_prefix_matches_binding") is True,
            "expected_value": expected_value,
            "recomputed_expected_value": expected_value,
            "matches_replay": not derived_replay.get("errors"),
            "mismatches": [],
            "quote_parse": quote_parse,
            "head_log_id": args.head_log_id,
            "sequence_num": derived_replay.get("sequence_num"),
            "mr_value": derived_replay.get("mr_value"),
            "head_event_digest": derived_replay.get("head_event_digest"),
            "errors": attested_errors,
            "contract_scope": "current-head binding only",
        },
        "fallback": None,
        "sources": {
            "immutable_backend": {
                "reachable": immutable_result.get("reachable", False),
                "success": immutable_success,
                "head_log_id": immutable_result.get("head_log_id"),
                "entry_count": immutable_data.get("entry_count", 0),
                "subject": immutable_data.get("subject"),
            },
            "trucon_chain": None,
        },
        "entries": replay_entries,
        "errors": errors,
    })


def _normalize_fallback_result(
    args: argparse.Namespace,
    chain_id: str,
    immutable_result: Dict[str, Any],
    fallback_result: Dict[str, Any],
) -> Dict[str, Any]:
    trucon_result = fallback_result["trucon"]
    chain_state = fallback_result["chain_state"]
    trucon_data = trucon_result.get("data") or {}
    immutable_data = immutable_result.get("details") or {}
    replay_entries = _normalize_replay_entries(immutable_data.get("entries", []))

    pending_count = trucon_data.get("rekor_pending", 0)
    total_entries = trucon_data.get("total_entries", immutable_data.get("entry_count", 0))
    tee_available = bool(trucon_data.get("rtmr_available")) if trucon_data else None
    verification_mode = "tee" if tee_available else "non_tee_fallback"
    status_detail = "tee-backed" if verification_mode == "tee" else "test-only"

    errors: List[str] = []
    immutable_success = immutable_result.get("success", False)
    trucon_reachable = trucon_result.get("reachable", False)
    trucon_valid = trucon_data.get("valid") if trucon_reachable else None

    if immutable_result.get("errors"):
        errors.extend(immutable_result["errors"])
    if trucon_result.get("error"):
        errors.append(trucon_result["error"])

    status = "verified"
    success = True
    if args.require_tee and verification_mode != "tee":
        success = False
        status = "failed"
        errors.append("TEE evidence was required but unavailable")
    elif not immutable_success and pending_count == 0:
        success = False
        status = "failed"
    elif trucon_reachable and trucon_valid is False:
        success = False
        status = "failed"
    elif args.fail_on_pending and pending_count > 0:
        success = False
        status = "failed"
        errors.append("Pending records present while --fail-on-pending is enabled")
    elif pending_count > 0:
        status = "incomplete"
    elif not trucon_reachable:
        success = immutable_success
        status = "degraded" if immutable_success else "failed"

    provenance_status, provenance_detail = _summarize_replay_provenance(replay_entries)
    verification_tier = _compute_verification_tier(provenance_status, False)

    return _attach_profile_results({
        "target": {
            "chain_id": chain_id,
            "head_log_id": chain_state.get("head_log_id"),
            "source": "internal-live-troubleshooting",
        },
        "mode": {
            "input_mode": "live-troubleshooting",
            "tee_required": args.require_tee,
            "tee_available": tee_available,
            "verification_mode": verification_mode,
            "status_detail": f"{status_detail}; troubleshooting-only",
            "fallback_used": True,
            "mirror_required": args.require_mirror,
            "mirror_configured": bool(args.mirror_dir),
        },
        "summary": {
            "success": success,
            "status": status,
            "verification_tier": verification_tier,
            "entry_count": total_entries,
            "confirmed_count": trucon_data.get("rekor_confirmed", immutable_data.get("entry_count", 0)),
            "pending_count": pending_count,
            "first_error_at": trucon_data.get("first_error_at"),
        },
        "replay": {
            "reachable": immutable_result.get("reachable", False),
            "success": immutable_success,
            "head_log_id": immutable_result.get("head_log_id"),
            "entry_count": immutable_data.get("entry_count", 0),
            "subject": immutable_data.get("subject"),
            "entries": replay_entries,
            "derived": None,
            "provenance": {
                "status": provenance_status,
                "detail": provenance_detail,
            },
        },
        "attested_head": {
            "present": False,
            "valid": None,
            "matches_replay": None,
            "errors": [],
            "contract_scope": None,
        },
        "fallback": {
            "reachable": trucon_reachable,
            "valid": trucon_valid,
            "rtmr_available": trucon_data.get("rtmr_available"),
            "head_mr_value": trucon_data.get("head_mr_value"),
            "entries": trucon_data.get("entries", []),
            "note": "explicit internal troubleshooting mode",
        },
        "sources": {
            "immutable_backend": {
                "reachable": immutable_result.get("reachable", False),
                "success": immutable_success,
                "head_log_id": immutable_result.get("head_log_id"),
                "entry_count": immutable_data.get("entry_count", 0),
                "subject": immutable_data.get("subject"),
            },
            "trucon_chain": {
                "reachable": trucon_reachable,
                "valid": trucon_valid,
                "rtmr_available": trucon_data.get("rtmr_available"),
            },
        },
        "entries": replay_entries,
        "errors": errors,
    })


def _render_text(result: Dict[str, Any]) -> str:
    attested_head = result.get("attested_head") or {}
    replay = result.get("replay") or {}
    fallback = result.get("fallback") or {}
    lines = [
        f"Chain: {result['target']['chain_id']}",
        f"Status: {result['summary']['status']}",
        f"Verification tier: {result['summary'].get('verification_tier')}",
        f"Mode: {result['mode']['input_mode']} -> {result['mode']['verification_mode']} ({result['mode']['status_detail']})",
        f"Entries: {result['summary']['entry_count']} total, {result['summary']['confirmed_count']} confirmed, {result['summary']['pending_count']} pending",
        "Replay:",
        f"  immutable_backend: reachable={replay.get('reachable')} success={replay.get('success')} head_log_id={replay.get('head_log_id')}",
    ]
    rollout_status, rollout_detail = _summarize_replay_rollout(replay.get("entries", []))
    provenance = replay.get("provenance") or {"status": "unavailable", "detail": "no replay provenance summary available"}
    lines.append(f"  rollout={rollout_status} {rollout_detail}")
    lines.append(f"  provenance={provenance.get('status')} {provenance.get('detail')}")
    if result["mode"].get("input_mode") == "quote-backed":
        lines.append("  trust_sources=public_replay(history, baseline) + direct_quote(current_head_binding)")
    else:
        lines.append("  trust_sources=public_replay(history, baseline) + exported_evidence(current_head_binding)")

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


def run_verification(args: argparse.Namespace) -> Dict[str, Any]:
    def _invalid_attested_result(input_mode: str, source: str, target_chain_id: Optional[str], message: str) -> Dict[str, Any]:
        return {
            "target": {"chain_id": target_chain_id, "source": source},
            "mode": {
                "input_mode": input_mode,
                "tee_required": args.require_tee,
                "tee_available": False,
                "verification_mode": input_mode,
                "status_detail": f"invalid-{source}",
                "fallback_used": False,
            },
            "summary": {
                "success": False,
                "status": "failed",
                "entry_count": 0,
                "confirmed_count": 0,
                "pending_count": 0,
                "first_error_at": None,
            },
            "replay": {
                "reachable": False,
                "success": False,
                "head_log_id": None,
                "entry_count": 0,
                "subject": None,
                "entries": [],
                "derived": None,
            },
            "attested_head": {
                "present": True,
                "valid": False,
                "matches_replay": None,
                "errors": [message],
            },
            "fallback": None,
            "sources": {"immutable_backend": None, "trucon_chain": None},
            "entries": [],
            "errors": [message],
        }

    evidence = None
    if args.evidence_path:
        try:
            evidence = _load_evidence(args)
        except Exception as exc:
            return _invalid_attested_result(
                "evidence-backed",
                "evidence-package",
                args.chain_id,
                f"Invalid evidence package: {exc}",
            )

    if evidence is not None:
        immutable_result = _load_immutable_result(args, evidence.chain_id, evidence.head_log_id)
        return _normalize_evidence_result(args, evidence, immutable_result)

    quote_input = None
    if args.quote_value:
        try:
            quote_input = _load_quote_value(args)
        except Exception as exc:
            return _invalid_attested_result(
                "quote-backed",
                "direct-quote",
                args.chain_id,
                f"Invalid quote input: {exc}",
            )

    if quote_input is not None:
        immutable_result = _load_immutable_result(args, args.chain_id, args.head_log_id)
        return _normalize_quote_result(args, quote_input, immutable_result)

    if not args.chain_id:
        raise ValueError("Either a chain_id, --evidence, or --quote must be provided")

    fallback_result = _run_fallback_verification(args, args.chain_id)
    chain_state = fallback_result["chain_state"]
    trucon_data = fallback_result["trucon"].get("data") or {}
    immutable_result = _load_immutable_result(args, args.chain_id, chain_state.get("head_log_id"))
    if not chain_state.get("head_log_id") and trucon_data.get("rekor_pending", 0) > 0:
        immutable_result = {
            "reachable": False,
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "entry_count": 0,
                "entries": [],
                "subject": f"trusted-log-chain_{args.chain_id}",
                "chain_id": args.chain_id,
            },
            "head_log_id": None,
        }
    return _normalize_fallback_result(args, args.chain_id, immutable_result, fallback_result)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.evidence_path and args.quote_value:
        parser.error("--evidence and --quote cannot be used together")
    if args.quote_value and not args.chain_id:
        parser.error("--quote requires a chain_id")
    if args.quote_value and not args.head_log_id:
        parser.error("--quote requires --head-log-id")
    if args.quote_value and args.troubleshoot_live:
        parser.error("--quote cannot be combined with --troubleshoot-live")
    if args.head_log_id and not args.quote_value:
        parser.error("--head-log-id is only supported with --quote")
    if not args.chain_id and not args.evidence_path and not args.quote_value:
        parser.error("--evidence is required for exported evidence verification, --quote for direct quote verification, or provide chain_id with --troubleshoot-live")
    if args.chain_id and not args.evidence_path and not args.quote_value and not args.troubleshoot_live:
        parser.error("Bare chain_id verification is no longer a supported external path; use --evidence or add --troubleshoot-live")
    if args.troubleshoot_live and not args.chain_id:
        parser.error("--troubleshoot-live requires a chain_id")

    result = run_verification(args)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_text(result))

    return 0 if result["summary"]["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
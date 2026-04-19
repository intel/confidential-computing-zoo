import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tc_api.config import TRUCON_SERVICE_TOKEN, TRUCON_URL
from tc_api.tlog_client import TrustedLogAPI
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter
from tc_api.trucon.evidence import compute_binding_expected_value, load_attested_head_evidence_json


def _fetch_trucon_json(path: str) -> Dict[str, Any]:
    url = f"{TRUCON_URL.rstrip('/')}{path}"
    request = urllib.request.Request(url, method="GET")
    if TRUCON_SERVICE_TOKEN:
        request.add_header("Authorization", f"Bearer {TRUCON_SERVICE_TOKEN}")

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify a trusted-log chain using exported evidence or a live fallback chain_id"
    )
    parser.add_argument("chain_id", nargs="?", help="Chain identifier to verify in live fallback mode")
    parser.add_argument(
        "--evidence",
        dest="evidence_path",
        help="Path to exported attested-head evidence JSON, or '-' to read from stdin",
    )
    parser.add_argument("--signer-identity", dest="signer_identity")
    parser.add_argument("--expected-entry-count", type=int, dest="expected_entry_count")
    parser.add_argument("--fail-on-pending", action="store_true")
    parser.add_argument("--require-tee", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _normalize_replay_entries(immutable_entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        {
            "index": entry.get("index"),
            "event_id": entry.get("event_id"),
            "event_type": entry.get("event_type"),
            "digest": entry.get("digest"),
            "created": entry.get("created"),
            "subject_names": entry.get("subject_names", []),
            "signer_identity": entry.get("signer_identity"),
            "signer_identity_match": entry.get("signer_identity_match"),
            "errors": entry.get("errors", []),
        }
        for entry in immutable_entries
    ]


def _entry_value(predicate_entries: List[Dict[str, Any]], key: str) -> Optional[str]:
    for entry in predicate_entries:
        if isinstance(entry, dict) and entry.get("key") == key:
            value = entry.get("value")
            return value if isinstance(value, str) else None
    return None


def _derive_replay_chain_state(immutable_result: Dict[str, Any]) -> Dict[str, Any]:
    immutable_data = immutable_result.get("details") or {}
    entries = list(reversed(immutable_data.get("entries", [])))
    derived = {
        "chain_id": immutable_data.get("chain_id"),
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

    baseline_entries = entries[0].get("predicate_entries") or []
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
        tlog = TrustedLogAPI(immutable_log=SigstoreLogAdapter(), trucon_url=TRUCON_URL)
        result = tlog.verify_record(
            head_log_id,
            policy={
                "chain_id": chain_id,
                "signer_identity": args.signer_identity,
                "expected_entry_count": args.expected_entry_count,
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
        },
        "summary": {
            "success": success,
            "status": status,
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
            "head_log_id": evidence.head_log_id,
            "sequence_num": evidence.sequence_num,
            "mr_value": evidence.mr_value,
            "head_event_digest": evidence.head_event_digest,
            "errors": attested_errors,
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
    return result


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

    return {
        "target": {
            "chain_id": chain_id,
            "head_log_id": chain_state.get("head_log_id"),
            "source": "live-chain-id-fallback",
        },
        "mode": {
            "input_mode": "live-fallback",
            "tee_required": args.require_tee,
            "tee_available": tee_available,
            "verification_mode": verification_mode,
            "status_detail": status_detail,
            "fallback_used": True,
        },
        "summary": {
            "success": success,
            "status": status,
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
        },
        "attested_head": {
            "present": False,
            "valid": None,
            "matches_replay": None,
            "errors": [],
        },
        "fallback": {
            "reachable": trucon_reachable,
            "valid": trucon_valid,
            "rtmr_available": trucon_data.get("rtmr_available"),
            "head_mr_value": trucon_data.get("head_mr_value"),
            "entries": trucon_data.get("entries", []),
            "note": "transitional live TruCon fallback",
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
    }


def _render_text(result: Dict[str, Any]) -> str:
    attested_head = result.get("attested_head") or {}
    replay = result.get("replay") or {}
    fallback = result.get("fallback") or {}
    lines = [
        f"Chain: {result['target']['chain_id']}",
        f"Status: {result['summary']['status']}",
        f"Mode: {result['mode']['input_mode']} -> {result['mode']['verification_mode']} ({result['mode']['status_detail']})",
        f"Entries: {result['summary']['entry_count']} total, {result['summary']['confirmed_count']} confirmed, {result['summary']['pending_count']} pending",
        "Replay:",
        f"  immutable_backend: reachable={replay.get('reachable')} success={replay.get('success')} head_log_id={replay.get('head_log_id')}",
    ]

    if attested_head.get("present"):
        lines.append("Attested head:")
        lines.append(
            "  "
            f"valid={attested_head.get('valid')} matches_replay={attested_head.get('matches_replay')} "
            f"freshness={attested_head.get('freshness')}"
        )
    elif result["mode"].get("fallback_used"):
        lines.append("Attested head:")
        lines.append("  not used (live fallback mode)")

    if result["mode"].get("fallback_used"):
        lines.append("Fallback:")
        lines.append(
            "  "
            f"reachable={fallback.get('reachable')} valid={fallback.get('valid')} rtmr_available={fallback.get('rtmr_available')}"
        )

    lines.append("Per-record replay detail:")

    for entry in replay.get("entries", []):
        lines.append(
            f"  - index={entry.get('index')} event_id={entry.get('event_id')} event_type={entry.get('event_type')} digest={entry.get('digest')}"
        )

    if result["errors"]:
        lines.append("Errors:")
        for error in result["errors"]:
            lines.append(f"  - {error}")

    return "\n".join(lines)


def run_verification(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        evidence = _load_evidence(args)
    except Exception as exc:
        target_chain_id = args.chain_id
        return {
            "target": {"chain_id": target_chain_id, "source": "evidence-package"},
            "mode": {
                "input_mode": "evidence-backed",
                "tee_required": args.require_tee,
                "tee_available": False,
                "verification_mode": "evidence-backed",
                "status_detail": "invalid-evidence",
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
                "errors": [f"Invalid evidence package: {exc}"],
            },
            "fallback": None,
            "sources": {"immutable_backend": None, "trucon_chain": None},
            "entries": [],
            "errors": [f"Invalid evidence package: {exc}"],
        }

    if evidence is not None:
        immutable_result = _load_immutable_result(args, evidence.chain_id, evidence.head_log_id)
        return _normalize_evidence_result(args, evidence, immutable_result)

    if not args.chain_id:
        raise ValueError("Either a chain_id or --evidence must be provided")

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
    if not args.chain_id and not args.evidence_path:
        parser.error("Either a chain_id or --evidence must be provided")

    result = run_verification(args)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_text(result))

    return 0 if result["summary"]["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
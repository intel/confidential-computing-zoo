import argparse
import json
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from tc_api.config import TRUCON_SERVICE_TOKEN, TRUCON_URL
from tc_api.tlog_client import TrustedLogAPI
from tc_api.trucon.adapters.sigstore import SigstoreLogAdapter


def _fetch_trucon_json(path: str) -> Dict[str, Any]:
    url = f"{TRUCON_URL.rstrip('/')}{path}"
    request = urllib.request.Request(url, method="GET")
    if TRUCON_SERVICE_TOKEN:
        request.add_header("Authorization", f"Bearer {TRUCON_SERVICE_TOKEN}")

    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify a trusted-log chain by chain_id")
    parser.add_argument("chain_id", help="Chain identifier to verify")
    parser.add_argument("--signer-identity", dest="signer_identity")
    parser.add_argument("--expected-entry-count", type=int, dest="expected_entry_count")
    parser.add_argument("--fail-on-pending", action="store_true")
    parser.add_argument("--require-tee", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _merge_entries(
    immutable_entries: List[Dict[str, Any]],
    trucon_entries: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    immutable_by_event_id = {
        entry.get("event_id"): entry for entry in immutable_entries if entry.get("event_id")
    }
    remaining_immutable = list(immutable_entries)

    for trucon_entry in trucon_entries:
        event_id = trucon_entry.get("event_id")
        immutable_entry = immutable_by_event_id.pop(event_id, None) if event_id else None
        if immutable_entry and immutable_entry in remaining_immutable:
            remaining_immutable.remove(immutable_entry)
        merged.append(
            {
                "seq": trucon_entry.get("seq"),
                "record_id": trucon_entry.get("record_id"),
                "event_id": event_id,
                "status": "confirmed" if trucon_entry.get("rekor_ok") else "pending",
                "trucon": {
                    "mr_ok": trucon_entry.get("mr_ok"),
                    "rekor_ok": trucon_entry.get("rekor_ok"),
                    "rtmr_extended": trucon_entry.get("rtmr_extended"),
                    "mr_value": trucon_entry.get("mr_value"),
                    "prev_log_id_ok": trucon_entry.get("prev_log_id_ok"),
                    "error": trucon_entry.get("error"),
                },
                "immutable_backend": immutable_entry,
            }
        )

    for immutable_entry in remaining_immutable:
        merged.append(
            {
                "seq": None,
                "record_id": None,
                "event_id": immutable_entry.get("event_id"),
                "status": "confirmed",
                "trucon": None,
                "immutable_backend": immutable_entry,
            }
        )

    return merged


def _normalize_result(args: argparse.Namespace, immutable_result: Dict[str, Any], trucon_result: Dict[str, Any]) -> Dict[str, Any]:
    trucon_data = trucon_result.get("data") or {}
    immutable_data = immutable_result.get("details") or {}
    immutable_entries = list(reversed(immutable_data.get("entries", [])))
    trucon_entries = trucon_data.get("entries", [])
    entries = _merge_entries(immutable_entries, trucon_entries)

    pending_count = trucon_data.get("rekor_pending", 0)
    total_entries = trucon_data.get("total_entries", len(entries))
    verification_mode = "unknown"
    tee_available = None
    if trucon_data:
        tee_available = bool(trucon_data.get("rtmr_available"))
        verification_mode = "tee" if tee_available else "non_tee_fallback"

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
        success = True
        status = "incomplete"
    elif not trucon_reachable:
        success = immutable_success
        status = "degraded" if immutable_success else "failed"

    if args.expected_entry_count is not None and total_entries != args.expected_entry_count:
        success = False
        status = "failed"
        errors.append(f"Expected {args.expected_entry_count} entries, got {total_entries}")

    if verification_mode == "non_tee_fallback":
        status_detail = "test-only"
    elif verification_mode == "tee":
        status_detail = "tee-backed"
    else:
        status_detail = "unknown"

    return {
        "target": {"chain_id": args.chain_id},
        "mode": {
            "tee_required": args.require_tee,
            "tee_available": tee_available,
            "verification_mode": verification_mode,
            "status_detail": status_detail,
        },
        "summary": {
            "success": success,
            "status": status,
            "entry_count": total_entries,
            "confirmed_count": trucon_data.get("rekor_confirmed", immutable_data.get("entry_count", 0)),
            "pending_count": pending_count,
            "first_error_at": trucon_data.get("first_error_at"),
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
        "entries": entries,
        "errors": errors,
    }


def _render_text(result: Dict[str, Any]) -> str:
    lines = [
        f"Chain: {result['target']['chain_id']}",
        f"Status: {result['summary']['status']}",
        f"Mode: {result['mode']['verification_mode']} ({result['mode']['status_detail']})",
        f"Entries: {result['summary']['entry_count']} total, {result['summary']['confirmed_count']} confirmed, {result['summary']['pending_count']} pending",
        "Sources:",
        f"  immutable_backend: reachable={result['sources']['immutable_backend']['reachable']} success={result['sources']['immutable_backend']['success']}",
        f"  trucon_chain: reachable={result['sources']['trucon_chain']['reachable']} valid={result['sources']['trucon_chain']['valid']}",
        "Per-record detail:",
    ]

    for entry in result["entries"]:
        lines.append(
            f"  - seq={entry['seq']} record_id={entry['record_id']} event_id={entry['event_id']} status={entry['status']}"
        )

    if result["errors"]:
        lines.append("Errors:")
        for error in result["errors"]:
            lines.append(f"  - {error}")

    return "\n".join(lines)


def run_verification(args: argparse.Namespace) -> Dict[str, Any]:
    trucon_result: Dict[str, Any] = {"reachable": False, "data": None, "error": None}
    chain_state: Dict[str, Any] = {}
    try:
        chain_state = _fetch_trucon_json(f"/chain-state/{args.chain_id}")
    except urllib.error.HTTPError as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: HTTP {exc.code}"
    except Exception as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: {exc}"

    try:
        trucon_result["data"] = _fetch_trucon_json(f"/verify-chain/{args.chain_id}")
        trucon_result["reachable"] = True
    except urllib.error.HTTPError as exc:
        trucon_result["error"] = f"TruCon verification failed: HTTP {exc.code}"
    except Exception as exc:
        trucon_result["error"] = f"TruCon verification failed: {exc}"

    immutable_result: Dict[str, Any]
    head_log_id = chain_state.get("head_log_id")
    if head_log_id:
        tlog = TrustedLogAPI(immutable_log=SigstoreLogAdapter(), trucon_url=TRUCON_URL)
        result = tlog.verify_record(
            head_log_id,
            policy={
                "chain_id": args.chain_id,
                "signer_identity": args.signer_identity,
            },
        )
        immutable_result = {
            "reachable": True,
            "success": result.success,
            "errors": result.errors,
            "details": result.details,
            "head_log_id": head_log_id,
        }
    elif trucon_result.get("data", {}).get("rekor_pending", 0) > 0:
        immutable_result = {
            "reachable": False,
            "success": True,
            "errors": [],
            "details": {
                "source": "immutable_backend",
                "entry_count": 0,
                "entries": [],
                "subject": f"trusted-log-chain_{args.chain_id}",
            },
            "head_log_id": None,
        }
    else:
        immutable_result = {
            "reachable": False,
            "success": False,
            "errors": [f"No confirmed immutable log head for chain '{args.chain_id}'"],
            "details": {
                "source": "immutable_backend",
                "entry_count": 0,
                "entries": [],
                "subject": f"trusted-log-chain_{args.chain_id}",
            },
            "head_log_id": None,
        }

    return _normalize_result(args, immutable_result, trucon_result)


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = run_verification(args)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_text(result))

    return 0 if result["summary"]["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
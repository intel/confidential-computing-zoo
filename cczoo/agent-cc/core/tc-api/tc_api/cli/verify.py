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
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from tc_api.config import TRUCON_SERVICE_TOKEN, TRUCON_URL
from tc_api.transparency.commit_client import TrustedLogAPI
from tlog.backends.rekor.adapter import SigstoreLogAdapter
from tc_api.trucon.evidence import (
    compute_binding_expected_value,
    load_attested_head_evidence_json,
)
from .verify_quote import (
    inspect_quote_binding as _inspect_quote_binding,
)
from .verify_replay import (
    attach_profile_results as _attach_profile_results,
    compute_verification_tier as _compute_verification_tier,
    derive_replay_chain_state as _derive_replay_chain_state,
    normalize_replay_entries as _normalize_replay_entries,
    summarize_replay_provenance as _summarize_replay_provenance,
)
from .verify_render import render_text as _render_text


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


def _format_timestamp(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _normalize_head_log_verification(
    immutable_result: Dict[str, Any],
    *,
    fallback_used: bool = False,
) -> Dict[str, Any]:
    immutable_data = immutable_result.get("details") or {}
    raw_head_log = immutable_data.get("head_log_verification") or {}
    head_log_id = immutable_result.get("head_log_id")
    bootstrap_trust = raw_head_log.get("bootstrap_trust") or {}
    raw_status = raw_head_log.get("status")
    if not raw_status:
        raw_status = "verified" if head_log_id else "unavailable"

    display_status = raw_status
    if fallback_used and raw_status in {"degraded", "unavailable"}:
        display_status = "troubleshooting-only"

    normalized = {
        "status": display_status,
        "raw_status": raw_status,
        "scope": raw_head_log.get("scope") or "accepted-head-only",
        "log_id": raw_head_log.get("log_id") or head_log_id,
        "entry_uuid": raw_head_log.get("entry_uuid"),
        "log_index": raw_head_log.get("log_index"),
        "inclusion_status": raw_head_log.get("inclusion_status") or ("verified" if head_log_id else "unavailable"),
        "checkpoint_status": raw_head_log.get("checkpoint_status") or ("verified" if head_log_id else "unavailable"),
        "checkpoint_origin": raw_head_log.get("checkpoint_origin"),
        "bootstrap_trust": {
            "configured": bool(bootstrap_trust.get("configured")),
            "source": bootstrap_trust.get("source"),
            "consistency_proven": bool(bootstrap_trust.get("consistency_proven")),
        },
        "proof": raw_head_log.get("proof"),
        "reasons": list(raw_head_log.get("reasons") or []),
        "limitations": [],
    }
    if (
        normalized["raw_status"] == "verified"
        and normalized["bootstrap_trust"]["configured"]
        and not normalized["bootstrap_trust"]["consistency_proven"]
    ):
        normalized["limitations"].append(
            "Accepted head inclusion is anchored to the configured bootstrap checkpoint trust only; historical consistency across time is not proven."
        )
    return normalized


def _head_log_failed(head_log_verification: Dict[str, Any]) -> bool:
    return head_log_verification.get("raw_status", head_log_verification.get("status")) == "failed"


def _head_log_degraded(head_log_verification: Dict[str, Any]) -> bool:
    return head_log_verification.get("raw_status", head_log_verification.get("status")) in {"degraded", "unavailable"}


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


def _run_fallback_verification(args: argparse.Namespace, chain_id: str) -> Dict[str, Any]:
    trucon_result: Dict[str, Any] = {"reachable": False, "data": None, "error": None}
    chain_state: Dict[str, Any] = {}
    try:
        chain_state = _fetch_trucon_json("/chain-state")
    except urllib.error.HTTPError as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: HTTP {exc.code}"
    except Exception as exc:
        trucon_result["error"] = f"TruCon chain-state lookup failed: {exc}"

    try:
        trucon_result["data"] = _fetch_trucon_json("/verify-chain")
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
    head_log_verification = _normalize_head_log_verification(immutable_result)
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
    if _head_log_failed(head_log_verification):
        success = False
        status = "failed"
    elif _head_log_degraded(head_log_verification) and success:
        success = False
        status = "degraded"
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
        "log_verification": head_log_verification,
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
    head_log_verification = _normalize_head_log_verification(immutable_result)
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
    if _head_log_failed(head_log_verification):
        success = False
        status = "failed"
    elif _head_log_degraded(head_log_verification) and success:
        success = False
        status = "degraded"
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
        "log_verification": head_log_verification,
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
    head_log_verification = _normalize_head_log_verification(immutable_result, fallback_used=True)
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
    elif _head_log_failed(head_log_verification):
        success = False
        status = "failed"
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
    elif _head_log_degraded(head_log_verification):
        success = False
        status = head_log_verification.get("status", "troubleshooting-only")
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
        "log_verification": head_log_verification,
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
            "log_verification": {
                "status": "unavailable",
                "raw_status": "unavailable",
                "scope": "accepted-head-only",
                "log_id": None,
                "entry_uuid": None,
                "log_index": None,
                "inclusion_status": "unavailable",
                "checkpoint_status": "unavailable",
                "checkpoint_origin": None,
                "bootstrap_trust": {
                    "configured": False,
                    "source": None,
                    "consistency_proven": False,
                },
                "proof": None,
                "reasons": [message],
                "limitations": [],
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
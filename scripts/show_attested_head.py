#!/usr/bin/env python3

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tc_api.trucon.evidence import load_attested_head_evidence_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Show a readable summary of exported attested-head evidence"
    )
    parser.add_argument(
        "--evidence",
        required=True,
        help="Path to exported attested-head evidence JSON",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the summary as JSON",
    )
    return parser


def _load_evidence(path: str):
    payload = Path(path).read_text(encoding="utf-8")
    return load_attested_head_evidence_json(payload)


def _format_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _quote_preview(quote: str, preview_chars: int = 24) -> dict[str, Any]:
    return {
        "chars": len(quote),
        "prefix": quote[:preview_chars],
        "suffix": quote[-preview_chars:] if len(quote) > preview_chars else quote,
    }


def _build_summary(evidence) -> dict[str, Any]:
    expires_at = _format_timestamp(evidence.expires_at)
    generated_at = _format_timestamp(evidence.generated_at)
    expired = False
    freshness = "no-expiry-bound"
    if evidence.expires_at is not None:
        comparison_value = evidence.expires_at
        if comparison_value.tzinfo is None:
            comparison_value = comparison_value.replace(tzinfo=timezone.utc)
        expired = comparison_value < datetime.now(timezone.utc)
        freshness = "expired" if expired else "bounded"

    return {
        "file": None,
        "chain": {
            "chain_id": evidence.chain_id,
            "sequence_num": evidence.sequence_num,
            "head_log_id": evidence.head_log_id,
            "head_event_digest": evidence.head_event_digest,
        },
        "tee": {
            "tee_type": evidence.tee_type,
            "quote_format": evidence.quote_format,
            "mr_value": evidence.mr_value,
            "quote": _quote_preview(evidence.quote),
        },
        "timing": {
            "generated_at": generated_at,
            "expires_at": expires_at,
            "freshness": freshness,
            "expired": expired,
        },
        "binding": {
            "algorithm": evidence.report_data_binding.algorithm,
            "bound_fields": evidence.report_data_binding.bound_fields,
            "expected_value": evidence.report_data_binding.expected_value,
        },
        "extensions": evidence.extensions,
        "version": evidence.version,
    }


def _render_text(summary: dict[str, Any]) -> str:
    lines = [
        f"Evidence file: {summary['file']}",
        f"Version: {summary['version']}",
        f"Chain: {summary['chain']['chain_id']}",
        f"Sequence: {summary['chain']['sequence_num']}",
        f"Head log id: {summary['chain']['head_log_id']}",
        f"Head event digest: {summary['chain']['head_event_digest']}",
        f"TEE type: {summary['tee']['tee_type']}",
        f"Quote format: {summary['tee']['quote_format']}",
        f"MR value: {summary['tee']['mr_value']}",
        (
            "Quote: "
            f"chars={summary['tee']['quote']['chars']} "
            f"prefix={summary['tee']['quote']['prefix']} "
            f"suffix={summary['tee']['quote']['suffix']}"
        ),
        f"Generated at: {summary['timing']['generated_at']}",
        f"Expires at: {summary['timing']['expires_at']}",
        f"Freshness: {summary['timing']['freshness']}",
        f"Binding algorithm: {summary['binding']['algorithm']}",
        "Binding fields: " + ", ".join(summary['binding']['bound_fields']),
        f"Binding expected value: {summary['binding']['expected_value']}",
    ]

    if summary["extensions"] is not None:
        lines.append("Extensions: " + json.dumps(summary["extensions"], ensure_ascii=False, sort_keys=True))
    else:
        lines.append("Extensions: none")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        evidence = _load_evidence(args.evidence)
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")

    summary = _build_summary(evidence)
    summary["file"] = args.evidence
    if args.json_output:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(_render_text(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
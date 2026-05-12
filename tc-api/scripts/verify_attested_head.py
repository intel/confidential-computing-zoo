#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

from tc_api.cli.verify import _render_text, run_verification
from tc_api.trucon.evidence import load_attested_head_evidence_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify exported attested-head evidence against an expected immutable head log id"
    )
    parser.add_argument(
        "--evidence",
        required=True,
        help="Path to exported attested-head evidence JSON",
    )
    parser.add_argument(
        "--expected-head-log-id",
        help="Optional expected immutable head_log_id for the evidence package",
    )
    parser.add_argument(
        "--expected-chain-id",
        help="Optional expected chain_id. Defaults to the chain_id embedded in the evidence.",
    )
    parser.add_argument(
        "--expected-sequence-num",
        type=int,
        help="Optional expected head sequence number.",
    )
    parser.add_argument("--mirror-dir", dest="mirror_dir")
    parser.add_argument("--require-mirror", action="store_true", dest="require_mirror")
    parser.add_argument("--require-tee", action="store_true")
    parser.add_argument("--json", action="store_true", dest="json_output")
    return parser


def _load_evidence(path: str):
    payload = Path(path).read_text(encoding="utf-8")
    return load_attested_head_evidence_json(payload)


def _validate_expected_inputs(args: argparse.Namespace, evidence) -> None:
    if args.expected_head_log_id and evidence.head_log_id != args.expected_head_log_id:
        raise ValueError(
            "Expected head_log_id does not match evidence: "
            f"expected={args.expected_head_log_id} actual={evidence.head_log_id}"
        )
    if args.expected_chain_id and evidence.chain_id != args.expected_chain_id:
        raise ValueError(
            "Expected chain_id does not match evidence: "
            f"expected={args.expected_chain_id} actual={evidence.chain_id}"
        )
    if args.expected_sequence_num is not None and evidence.sequence_num != args.expected_sequence_num:
        raise ValueError(
            "Expected sequence_num does not match evidence: "
            f"expected={args.expected_sequence_num} actual={evidence.sequence_num}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        evidence = _load_evidence(args.evidence)
        _validate_expected_inputs(args, evidence)
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")

    verify_args = argparse.Namespace(
        chain_id=evidence.chain_id,
        evidence_path=args.evidence,
        troubleshoot_live=False,
        signer_identity=None,
        expected_entry_count=None,
        fail_on_pending=False,
        require_tee=args.require_tee,
        mirror_dir=args.mirror_dir,
        require_mirror=args.require_mirror,
        json_output=args.json_output,
    )

    result = run_verification(verify_args)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_render_text(result))

    return 0 if result["summary"]["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
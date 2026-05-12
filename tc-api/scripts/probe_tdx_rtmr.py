#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
from typing import Any


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(REPO_ROOT, "src")
if SRC_ROOT not in sys.path:
    sys.path.insert(0, SRC_ROOT)

from tc_api.trucon.adapters.tdx_mr import TdxMRAdapter  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Probe TDX RTMR support on the current host. By default this is read-only. "
            "Pass --execute-extend to perform one real extend and verify the result."
        )
    )
    parser.add_argument("--index", type=int, default=2, help="RTMR index to probe (default: 2)")
    parser.add_argument(
        "--sysfs-base-path",
        default="/sys/class/misc/tdx_guest/measurements/rtmr",
        help="RTMR sysfs base path prefix",
    )
    parser.add_argument(
        "--digest",
        default=None,
        help=(
            "48-byte sha384 hex digest to extend. If omitted, a deterministic probe digest is generated. "
            "Used only with --execute-extend."
        ),
    )
    parser.add_argument(
        "--execute-extend",
        action="store_true",
        help="Perform one real RTMR extend and verify the new value matches sha384(prev || digest)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the probe result as JSON",
    )
    return parser


def _default_digest(index: int) -> str:
    seed = f"tc-api-rtmr-probe:{index}".encode("utf-8")
    return hashlib.sha384(seed).hexdigest()


def _probe(args: argparse.Namespace) -> dict[str, Any]:
    adapter = TdxMRAdapter(sysfs_base_path=args.sysfs_base_path)
    sysfs_available = TdxMRAdapter.is_available(args.index, sysfs_base_path=args.sysfs_base_path)
    extend_available = TdxMRAdapter.is_extend_available(args.index, sysfs_base_path=args.sysfs_base_path)
    tdreport_read_available = TdxMRAdapter.is_report_read_available(args.index)
    digest = (args.digest or _default_digest(args.index)).removeprefix("sha384:")

    result: dict[str, Any] = {
        "index": args.index,
        "sysfs_base_path": args.sysfs_base_path,
        "sysfs_available": sysfs_available,
        "extend_available": extend_available,
        "tdreport_read_available": tdreport_read_available,
        "extend_ready_via_current_startup_logic": extend_available,
        "adapter_extend_method_can_fallback_to_libtdx_attest": True,
        "digest": f"sha384:{digest}",
    }

    try:
        current_value = adapter.read(args.index)
        result["read_ok"] = True
        result["current_value"] = current_value
    except Exception as exc:
        result["read_ok"] = False
        result["read_error"] = str(exc)
        return result

    if not args.execute_extend:
        return result

    try:
        new_value, prev_value = adapter.extend(args.index, digest)
        expected_value = hashlib.sha384(bytes.fromhex(prev_value) + bytes.fromhex(digest)).hexdigest()
        result.update(
            {
                "extend_attempted": True,
                "prev_value": prev_value,
                "new_value": new_value,
                "expected_value": expected_value,
                "extend_ok": new_value == expected_value,
            }
        )
    except Exception as exc:
        result.update(
            {
                "extend_attempted": True,
                "extend_ok": False,
                "extend_error": str(exc),
            }
        )

    return result


def main() -> int:
    args = _build_parser().parse_args()
    result = _probe(args)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")

    if args.execute_extend:
        return 0 if result.get("extend_ok") else 1
    return 0 if result.get("read_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
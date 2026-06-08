#!/usr/bin/env python3

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
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from tc_api.cli.verify import _render_text, run_verification
from tc_api.config import TRUCON_SERVICE_TOKEN, TRUCON_URL
from tc_api.trucon.evidence import load_attested_head_evidence_json


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch the current attested head from TruCon and verify it through the direct quote-backed path"
    )
    parser.add_argument(
        "chain_id",
        help="Chain identifier to fetch from the local TruCon evidence endpoint",
    )
    parser.add_argument(
        "--trucon-url",
        default=TRUCON_URL,
        help="Base URL for TruCon. Defaults to the current tc_api configuration.",
    )
    parser.add_argument(
        "--trucon-service-token",
        dest="trucon_service_token",
        help="Bearer token for the TruCon evidence endpoint. Defaults to TRUCON_SERVICE_TOKEN or the running tc_api process environment.",
    )
    parser.add_argument(
        "--tc-api-pid-file",
        default="logs/pids/tc_api.pid",
        help="Path to the tc_api pid file used to recover TRUCON_SERVICE_TOKEN when it is not passed explicitly.",
    )
    parser.add_argument(
        "--expected-head-log-id",
        help="Optional expected immutable head_log_id for the fetched attested head.",
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


def _read_running_trucon_service_token(pid_file: str) -> str | None:
    pid_path = Path(pid_file)
    if not pid_path.exists():
        return None

    pid_text = pid_path.read_text(encoding="utf-8").strip()
    if not pid_text:
        return None

    environ_path = Path("/proc") / pid_text / "environ"
    if not environ_path.exists():
        return None

    for item in environ_path.read_bytes().split(b"\0"):
        if item.startswith(b"TRUCON_SERVICE_TOKEN="):
            return item.split(b"=", 1)[1].decode("utf-8")
    return None


def _resolve_trucon_service_token(args: argparse.Namespace) -> str | None:
    if args.trucon_service_token:
        return args.trucon_service_token
    if TRUCON_SERVICE_TOKEN:
        return TRUCON_SERVICE_TOKEN
    if os.environ.get("TRUCON_SERVICE_TOKEN"):
        return os.environ["TRUCON_SERVICE_TOKEN"]
    return _read_running_trucon_service_token(args.tc_api_pid_file)


def _fetch_current_evidence(args: argparse.Namespace) -> str:
    token = _resolve_trucon_service_token(args)
    url = f"{args.trucon_url.rstrip('/')}/evidence"
    request = urllib.request.Request(url, method="GET")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def _validate_expected_inputs(args: argparse.Namespace, evidence) -> None:
    if evidence.chain_id != args.chain_id:
        raise ValueError(
            f"Fetched evidence chain_id did not match request: requested={args.chain_id} actual={evidence.chain_id}"
        )
    if args.expected_head_log_id and evidence.head_log_id != args.expected_head_log_id:
        raise ValueError(
            "Expected head_log_id does not match fetched attested head: "
            f"expected={args.expected_head_log_id} actual={evidence.head_log_id}"
        )
    if args.expected_sequence_num is not None and evidence.sequence_num != args.expected_sequence_num:
        raise ValueError(
            "Expected sequence_num does not match fetched attested head: "
            f"expected={args.expected_sequence_num} actual={evidence.sequence_num}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        payload = _fetch_current_evidence(args)
        evidence = load_attested_head_evidence_json(payload)
        _validate_expected_inputs(args, evidence)
    except urllib.error.HTTPError as exc:
        parser.exit(1, f"Error: TruCon evidence request failed: HTTP {exc.code}\n")
    except urllib.error.URLError as exc:
        parser.exit(1, f"Error: TruCon evidence request failed: {exc.reason}\n")
    except Exception as exc:
        parser.exit(1, f"Error: {exc}\n")

    verify_args = argparse.Namespace(
        chain_id=evidence.chain_id,
        evidence_path=None,
        quote_value=evidence.quote,
        head_log_id=evidence.head_log_id,
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
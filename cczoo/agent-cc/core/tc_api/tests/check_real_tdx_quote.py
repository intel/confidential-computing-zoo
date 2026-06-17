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
import ctypes
import importlib.util
import json
import sys
from pathlib import Path

from tc_api.trucon.evidence import decode_binding_expected_value


TDX_ERROR_NAMES = {
    0x0000: "TDX_ATTEST_SUCCESS",
    0x0001: "TDX_ATTEST_ERROR_UNEXPECTED",
    0x0002: "TDX_ATTEST_ERROR_INVALID_PARAMETER",
    0x0003: "TDX_ATTEST_ERROR_OUT_OF_MEMORY",
    0x0004: "TDX_ATTEST_ERROR_VSOCK_FAILURE",
    0x0005: "TDX_ATTEST_ERROR_REPORT_FAILURE",
    0x0006: "TDX_ATTEST_ERROR_EXTEND_FAILURE",
    0x0007: "TDX_ATTEST_ERROR_NOT_SUPPORTED",
    0x0008: "TDX_ATTEST_ERROR_QUOTE_FAILURE",
    0x0009: "TDX_ATTEST_ERROR_BUSY",
    0x000A: "TDX_ATTEST_ERROR_DEVICE_FAILURE",
    0x000B: "TDX_ATTEST_ERROR_INVALID_RTMR_INDEX",
    0x000C: "TDX_ATTEST_ERROR_UNSUPPORTED_ATT_KEY_ID",
}


class TdxUuid(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 16)]


class TdxReportData(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 64)]


class TdxReport(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 1024)]


def _load_repo_quote_module(repo_root: Path):
    module_path = repo_root / "src" / "tc_api" / "trucon" / "adapters" / "tdx_quote.py"
    spec = importlib.util.spec_from_file_location("repo_tdx_quote", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_expected_value() -> str:
    return "head_log_id_bytes:" + b"tc-api-real-tdx-quote-check".hex()


def _hex_prefix(raw: bytes, size: int = 16) -> str:
    return raw[:size].hex()


def run_repo_adapter_check(repo_root: Path, expected_value: str) -> dict:
    module = _load_repo_quote_module(repo_root)
    adapter = module.TdxQuoteAdapter()
    result = {
        "report_data_path": adapter.report_data_path,
        "quote_path": adapter.quote_path,
        "quote_format": adapter.quote_format,
        "report_data_path_exists": Path(adapter.report_data_path).exists(),
        "quote_path_exists": Path(adapter.quote_path).exists(),
    }
    try:
        quote_material = adapter.quote(expected_value)
        quote_bytes = __import__("base64").b64decode(quote_material.quote)
        result.update(
            {
                "ok": True,
                "report_data": quote_material.report_data,
                "quote_size": len(quote_bytes),
                "quote_prefix": _hex_prefix(quote_bytes),
            }
        )
    except Exception as exc:
        result.update(
            {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
        )
    return result


def run_libtdx_probe(expected_value: str) -> dict:
    lib = ctypes.CDLL("libtdx_attest.so")
    lib.tdx_att_get_report.argtypes = [ctypes.POINTER(TdxReportData), ctypes.POINTER(TdxReport)]
    lib.tdx_att_get_report.restype = ctypes.c_uint32
    lib.tdx_att_get_quote.argtypes = [
        ctypes.POINTER(TdxReportData),
        ctypes.POINTER(TdxUuid),
        ctypes.c_uint32,
        ctypes.POINTER(TdxUuid),
        ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_uint32,
    ]
    lib.tdx_att_get_quote.restype = ctypes.c_uint32
    lib.tdx_att_free_quote.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    lib.tdx_att_free_quote.restype = ctypes.c_uint32

    report_data = TdxReportData()
    raw = decode_binding_expected_value(expected_value)
    for index, byte in enumerate(raw):
        report_data.d[index] = byte

    report = TdxReport()
    report_error = lib.tdx_att_get_report(ctypes.byref(report_data), ctypes.byref(report))
    result = {
        "report_code": f"0x{report_error:04x}",
        "report_name": TDX_ERROR_NAMES.get(report_error, "TDX_ATTEST_ERROR_UNKNOWN"),
    }
    if report_error != 0:
        result["ok"] = False
        return result

    selected_key = TdxUuid()
    quote_ptr = ctypes.POINTER(ctypes.c_uint8)()
    quote_size = ctypes.c_uint32()
    quote_error = lib.tdx_att_get_quote(
        ctypes.byref(report_data),
        None,
        0,
        ctypes.byref(selected_key),
        ctypes.byref(quote_ptr),
        ctypes.byref(quote_size),
        0,
    )
    result.update(
        {
            "quote_code": f"0x{quote_error:04x}",
            "quote_name": TDX_ERROR_NAMES.get(quote_error, "TDX_ATTEST_ERROR_UNKNOWN"),
            "quote_size": int(quote_size.value),
        }
    )
    if quote_error != 0 or not bool(quote_ptr):
        result["ok"] = False
        return result

    quote_bytes = ctypes.string_at(quote_ptr, quote_size.value)
    lib.tdx_att_free_quote(quote_ptr)
    result.update(
        {
            "ok": True,
            "quote_prefix": _hex_prefix(quote_bytes),
        }
    )
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check whether the repository's TDX quote acquisition works on the current TD VM")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--expected-value", default=_default_expected_value())
    parser.add_argument("--skip-libtdx-probe", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()

    summary = {
        "repo_root": str(repo_root),
        "expected_value": args.expected_value,
        "repo_adapter": run_repo_adapter_check(repo_root, args.expected_value),
    }
    if not args.skip_libtdx_probe:
        try:
            summary["libtdx_probe"] = run_libtdx_probe(args.expected_value)
        except Exception as exc:
            summary["libtdx_probe"] = {
                "ok": False,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    print(json.dumps(summary, ensure_ascii=True, indent=2))

    if summary["repo_adapter"].get("ok"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
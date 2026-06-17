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

import base64
import struct
from typing import Any, Dict, Optional

from tc_api.trucon.evidence import decode_binding_expected_value

_TDX_QUOTE_HEADER_SIZE = 48
_TDX_QUOTE_V4_BODY_SIZE = 584
_TDX_QUOTE_V5_DESCRIPTOR_SIZE = 6
_TDX_QUOTE_REPORT_DATA_START = 0x208
_TDX_QUOTE_REPORT_DATA_END = 0x248
_TDX_QUOTE_RTMR_START = 0x148
_TDX_QUOTE_RTMR_COUNT = 4
_TDX_QUOTE_RTMR_SIZE = 48
_TDX_QUOTE_SUPPORTED_VERSIONS = {4, 5}


def parse_tdx_quote(quote_b64: str) -> Dict[str, Any]:
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
def inspect_quote_binding(
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
        parsed = parse_tdx_quote(quote_b64)
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

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
import ctypes
import os
import uuid
from dataclasses import dataclass
from ctypes.util import find_library

from tc_api.trucon.evidence import decode_binding_expected_value


@dataclass(frozen=True)
class QuoteMaterial:
    quote: str
    report_data: str
    quote_format: str


class _TdxUuid(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 16)]


class _TdxReportData(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 64)]


class _TdxReport(ctypes.Structure):
    _fields_ = [("d", ctypes.c_uint8 * 1024)]


_TDX_REPORT_DATA_SIZE = 64


def _load_tdx_attest_library(attest_library_path: str):
    candidate_paths = []
    seen = set()

    def add_candidate(value: str | None):
        if not value:
            return
        normalized = value.strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        candidate_paths.append(normalized)

    add_candidate(attest_library_path)
    add_candidate(find_library("tdx_attest"))
    add_candidate("libtdx_attest.so.1")
    add_candidate("/usr/lib/x86_64-linux-gnu/libtdx_attest.so.1")
    add_candidate("/usr/lib64/libtdx_attest.so.1")
    add_candidate("/usr/lib/libtdx_attest.so.1")

    last_error: OSError | None = None
    for candidate in candidate_paths:
        try:
            return ctypes.CDLL(candidate)
        except OSError as exc:
            last_error = exc

    if last_error is not None:
        raise last_error
    raise OSError("libtdx_attest could not be located")


class TdxQuoteAdapter:
    """Generate quote material through TSM/configfs or libtdx_attest."""

    def __init__(
        self,
        report_data_path: str | None = None,
        quote_path: str | None = None,
        report_root_path: str | None = None,
        quote_format: str | None = None,
        attest_library_path: str | None = None,
    ) -> None:
        self.report_data_path = report_data_path or os.environ.get(
            "TRUCON_TSM_REPORT_DATA_PATH",
            "/sys/kernel/config/tsm/report/reportdata",
        )
        self.quote_path = quote_path or os.environ.get(
            "TRUCON_TSM_QUOTE_PATH",
            "/sys/kernel/config/tsm/report/outblob",
        )
        self.report_root_path = report_root_path or os.environ.get(
            "TRUCON_TSM_REPORT_ROOT",
            "/sys/kernel/config/tsm/report",
        )
        self.quote_format = quote_format or os.environ.get(
            "TRUCON_TSM_QUOTE_FORMAT",
        )
        self.attest_library_path = attest_library_path or os.environ.get(
            "TRUCON_TDX_ATTEST_LIB",
            "libtdx_attest.so",
        )

    @staticmethod
    def _normalize_report_data(expected_value: str) -> tuple[bytes, str]:
        if expected_value.startswith("sha384:"):
            raw = bytes.fromhex(expected_value.removeprefix("sha384:"))
        else:
            raw = decode_binding_expected_value(expected_value)
        if len(raw) > _TDX_REPORT_DATA_SIZE:
            raise ValueError("expected_value must encode at most 64 bytes")
        return raw, expected_value

    def _resolve_quote_format(self, backend_name: str) -> str:
        if self.quote_format:
            return self.quote_format
        if backend_name == "libtdx_attest":
            return "tdx-libtdx-attest"
        return "tdx-configfs-tsm"

    @staticmethod
    def _encode_tsm_inblob(report_data: bytes) -> bytes:
        if len(report_data) > _TDX_REPORT_DATA_SIZE:
            raise ValueError("TSM report data must not exceed 64 bytes")
        return report_data.ljust(_TDX_REPORT_DATA_SIZE, b"\x00")

    def _quote_via_tsm(self, report_data: bytes, expected_value: str) -> QuoteMaterial:
        tsm_inblob = self._encode_tsm_inblob(report_data)
        if not os.path.exists(self.report_data_path):
            raise FileNotFoundError(f"TSM reportdata path missing: {self.report_data_path}")
        if not os.path.exists(self.quote_path):
            raise FileNotFoundError(f"TSM quote path missing: {self.quote_path}")

        with open(self.report_data_path, "wb") as report_file:
            report_file.write(tsm_inblob)

        with open(self.report_data_path, "rb") as report_file:
            accepted_report_data = report_file.read()

        with open(self.quote_path, "rb") as quote_file:
            quote_bytes = quote_file.read()

        if accepted_report_data[: len(report_data)] != report_data:
            raise RuntimeError("TSM reportdata path did not retain the expected binding prefix")

        return QuoteMaterial(
            quote=base64.b64encode(quote_bytes).decode("ascii"),
            report_data=expected_value,
            quote_format=self._resolve_quote_format("tsm"),
        )

    def _quote_via_tsm_report_instance(self, report_data: bytes, expected_value: str) -> QuoteMaterial:
        tsm_inblob = self._encode_tsm_inblob(report_data)
        if not os.path.isdir(self.report_root_path):
            raise FileNotFoundError(f"TSM report root missing: {self.report_root_path}")

        report_dir = os.path.join(self.report_root_path, f"report0_{uuid.uuid4().hex}")
        os.mkdir(report_dir)
        try:
            report_data_path = os.path.join(report_dir, "inblob")
            quote_path = os.path.join(report_dir, "outblob")
            if not os.path.exists(report_data_path):
                raise FileNotFoundError(f"TSM report inblob path missing: {report_data_path}")
            if not os.path.exists(quote_path):
                raise FileNotFoundError(f"TSM report outblob path missing: {quote_path}")

            with open(report_data_path, "wb") as report_file:
                report_file.write(tsm_inblob)

            with open(quote_path, "rb") as quote_file:
                quote_bytes = quote_file.read()

            return QuoteMaterial(
                quote=base64.b64encode(quote_bytes).decode("ascii"),
                report_data=expected_value,
                quote_format=self._resolve_quote_format("tsm"),
            )
        finally:
            try:
                for entry_name in os.listdir(report_dir):
                    entry_path = os.path.join(report_dir, entry_name)
                    try:
                        os.unlink(entry_path)
                    except OSError:
                        pass
                os.rmdir(report_dir)
            except FileNotFoundError:
                pass

    def _load_attest_library(self):
        library = _load_tdx_attest_library(self.attest_library_path)
        library.tdx_att_get_report.argtypes = [ctypes.POINTER(_TdxReportData), ctypes.POINTER(_TdxReport)]
        library.tdx_att_get_report.restype = ctypes.c_uint32
        library.tdx_att_get_quote.argtypes = [
            ctypes.POINTER(_TdxReportData),
            ctypes.POINTER(_TdxUuid),
            ctypes.c_uint32,
            ctypes.POINTER(_TdxUuid),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
            ctypes.POINTER(ctypes.c_uint32),
            ctypes.c_uint32,
        ]
        library.tdx_att_get_quote.restype = ctypes.c_uint32
        library.tdx_att_free_quote.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
        library.tdx_att_free_quote.restype = ctypes.c_uint32
        return library

    def _quote_via_libtdx_attest(self, report_data: bytes, expected_value: str) -> QuoteMaterial:
        library = self._load_attest_library()

        tdx_report_data = _TdxReportData()
        for index, byte in enumerate(report_data):
            tdx_report_data.d[index] = byte

        tdx_report = _TdxReport()
        report_error = library.tdx_att_get_report(ctypes.byref(tdx_report_data), ctypes.byref(tdx_report))
        if report_error != 0:
            raise RuntimeError(f"libtdx_attest get_report failed with code 0x{report_error:04x}")

        selected_key = _TdxUuid()
        quote_ptr = ctypes.POINTER(ctypes.c_uint8)()
        quote_size = ctypes.c_uint32()
        quote_error = library.tdx_att_get_quote(
            ctypes.byref(tdx_report_data),
            None,
            0,
            ctypes.byref(selected_key),
            ctypes.byref(quote_ptr),
            ctypes.byref(quote_size),
            0,
        )
        if quote_error != 0 or not bool(quote_ptr):
            raise RuntimeError(f"libtdx_attest get_quote failed with code 0x{quote_error:04x}")

        try:
            quote_bytes = ctypes.string_at(quote_ptr, quote_size.value)
        finally:
            library.tdx_att_free_quote(quote_ptr)

        return QuoteMaterial(
            quote=base64.b64encode(quote_bytes).decode("ascii"),
            report_data=expected_value,
            quote_format=self._resolve_quote_format("libtdx_attest"),
        )

    def quote(self, expected_value: str) -> QuoteMaterial:
        report_data, normalized_expected_value = self._normalize_report_data(expected_value)
        if os.path.exists(self.report_data_path) and os.path.exists(self.quote_path):
            return self._quote_via_tsm(report_data, normalized_expected_value)
        if os.path.isdir(self.report_root_path):
            return self._quote_via_tsm_report_instance(report_data, normalized_expected_value)
        return self._quote_via_libtdx_attest(report_data, normalized_expected_value)
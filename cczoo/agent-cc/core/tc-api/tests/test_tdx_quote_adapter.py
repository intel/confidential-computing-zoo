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
import importlib.util
import os
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tc_api" / "trucon" / "adapters" / "tdx_quote.py"
SPEC = importlib.util.spec_from_file_location("repo_tdx_quote", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load quote adapter module from {MODULE_PATH}")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
TdxQuoteAdapter = MODULE.TdxQuoteAdapter


class FakeFunction:
    def __init__(self, callback):
        self.callback = callback
        self.argtypes = None
        self.restype = None

    def __call__(self, *args, **kwargs):
        return self.callback(*args, **kwargs)


class FakeLibTdxAttest:
    def __init__(self, quote_bytes: bytes, report_error: int = 0, quote_error: int = 0):
        self.quote_bytes = quote_bytes
        self.report_error = report_error
        self.quote_error = quote_error
        self._buffers = []
        self.tdx_att_get_report = FakeFunction(self._get_report)
        self.tdx_att_get_quote = FakeFunction(self._get_quote)
        self.tdx_att_free_quote = FakeFunction(self._free_quote)

    def _get_report(self, report_data_ptr, report_ptr):
        return self.report_error

    def _get_quote(self, report_data_ptr, att_key_id_list, list_size, selected_key_ptr, quote_ptr_ptr, quote_size_ptr, flags):
        if self.quote_error != 0:
            return self.quote_error

        buffer_type = ctypes.c_uint8 * len(self.quote_bytes)
        buffer = buffer_type(*self.quote_bytes)
        self._buffers.append(buffer)
        quote_ptr_ref = ctypes.cast(quote_ptr_ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)))
        quote_ptr_ref[0] = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_uint8))
        quote_size_ref = ctypes.cast(quote_size_ptr, ctypes.POINTER(ctypes.c_uint32))
        quote_size_ref[0] = len(self.quote_bytes)
        return 0

    def _free_quote(self, quote_ptr):
        return 0


def test_quote_uses_configfs_when_paths_exist(tmp_path):
    report_data_path = tmp_path / "reportdata"
    quote_path = tmp_path / "outblob"
    report_data_path.write_bytes(b"")
    quote_path.write_bytes(b"quote-bytes")

    expected_value = "head_log_id_bytes:" + ("12" * 24)
    expected_bytes = bytes.fromhex(expected_value.removeprefix("head_log_id_bytes:"))

    adapter = TdxQuoteAdapter(
        report_data_path=str(report_data_path),
        quote_path=str(quote_path),
        report_root_path=str(tmp_path / "missing-report-root"),
    )

    result = adapter.quote(expected_value)

    assert report_data_path.read_bytes() == expected_bytes + (b"\x00" * (64 - len(expected_bytes)))
    assert result.report_data == expected_value
    assert base64.b64decode(result.quote) == b"quote-bytes"
    assert result.quote_format == "tdx-configfs-tsm"


def test_quote_falls_back_to_libtdx_attest(monkeypatch):
    expected_value = "head_log_id_bytes:" + ("34" * 24)
    fake_library = FakeLibTdxAttest(b"real-quote")

    adapter = TdxQuoteAdapter(
        report_data_path="/missing/reportdata",
        quote_path="/missing/outblob",
        report_root_path="/missing/reportroot",
    )
    monkeypatch.setattr(adapter, "_load_attest_library", lambda: fake_library)

    result = adapter.quote(expected_value)

    assert result.report_data == expected_value
    assert base64.b64decode(result.quote) == b"real-quote"
    assert result.quote_format == "tdx-libtdx-attest"


def test_quote_preserves_legacy_sha384_binding(monkeypatch):
    expected_value = "sha384:" + ("34" * 48)
    fake_library = FakeLibTdxAttest(b"real-quote")

    adapter = TdxQuoteAdapter(
        report_data_path="/missing/reportdata",
        quote_path="/missing/outblob",
        report_root_path="/missing/reportroot",
    )
    monkeypatch.setattr(adapter, "_load_attest_library", lambda: fake_library)

    result = adapter.quote(expected_value)

    assert result.report_data == expected_value
    assert base64.b64decode(result.quote) == b"real-quote"


def test_quote_uses_dynamic_configfs_report_instance(tmp_path, monkeypatch):
    report_root = tmp_path / "report"
    report_root.mkdir()

    original_mkdir = os.mkdir

    def fake_mkdir(path, mode=0o777):
        original_mkdir(path, mode)
        created = Path(path)
        (created / "inblob").write_bytes(b"")
        (created / "outblob").write_bytes(b"instance-quote")
        (created / "provider").write_text("tdx_guest\n")
        (created / "generation").write_text("1\n")

    monkeypatch.setattr(MODULE.os, "mkdir", fake_mkdir)

    expected_value = "head_log_id_bytes:" + ("9a" * 24)
    adapter = TdxQuoteAdapter(
        report_data_path=str(report_root / "missing-reportdata"),
        quote_path=str(report_root / "missing-outblob"),
        report_root_path=str(report_root),
    )

    result = adapter.quote(expected_value)

    assert result.report_data == expected_value
    assert base64.b64decode(result.quote) == b"instance-quote"
    assert result.quote_format == "tdx-configfs-tsm"
    assert list(report_root.iterdir()) == []


def test_quote_raises_when_libtdx_attest_report_fails(monkeypatch):
    expected_value = "head_log_id_bytes:" + ("56" * 24)
    fake_library = FakeLibTdxAttest(b"", report_error=5)

    adapter = TdxQuoteAdapter(
        report_data_path="/missing/reportdata",
        quote_path="/missing/outblob",
        report_root_path="/missing/reportroot",
    )
    monkeypatch.setattr(adapter, "_load_attest_library", lambda: fake_library)

    try:
        adapter.quote(expected_value)
    except RuntimeError as exc:
        assert "get_report failed" in str(exc)
    else:
        raise AssertionError("Expected libtdx_attest report failure")


def test_quote_adapter_loads_versioned_libtdx_attest_when_unversioned_name_is_missing(monkeypatch):
    attempted = []
    fake_library = FakeLibTdxAttest(b"real-quote")

    def fake_cdll(path):
        attempted.append(path)
        if path == "libtdx_attest.so":
            raise OSError("missing unversioned soname")
        if path == "/usr/lib/x86_64-linux-gnu/libtdx_attest.so.1":
            return fake_library
        raise OSError(f"unexpected path: {path}")

    monkeypatch.setattr(MODULE, "find_library", lambda _name: "/usr/lib/x86_64-linux-gnu/libtdx_attest.so.1")
    monkeypatch.setattr(MODULE.ctypes, "CDLL", fake_cdll)

    adapter = TdxQuoteAdapter(
        report_data_path="/missing/reportdata",
        quote_path="/missing/outblob",
        report_root_path="/missing/reportroot",
    )

    result = adapter.quote("head_log_id_bytes:" + ("34" * 24))

    assert attempted[:2] == ["libtdx_attest.so", "/usr/lib/x86_64-linux-gnu/libtdx_attest.so.1"]
    assert base64.b64decode(result.quote) == b"real-quote"
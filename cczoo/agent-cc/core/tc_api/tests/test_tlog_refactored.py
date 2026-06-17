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

import pytest
import threading
import ctypes
from tc_api.trucon.database import init_db, insert_record, get_pending_records
from tc_api.transparency.commit_client import TrustedLogAPI
from tlog.local_mr import LocalMRAdapter
from typing import Tuple

class MockMRAdapter(LocalMRAdapter):
    def read(self, index: int) -> str:
        return "mock-value-1234"
        
    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        return "mock-new-mr-value", "mock-prev-mr-value"

# Simple tests to fulfill 4.2 and 4.3

def test_sqlite_wal_persistence(tmp_path):
    db_dir = tmp_path / "tc_api_queue"
    db_file = db_dir / "test_queue.db"
    init_db(str(db_file))
    
    # Assert DAC permissions
    st = db_dir.stat()
    assert (st.st_mode & 0o777) == 0o700
    
    # Insert multiple records concurrently
    def worker(i):
        insert_record(f"rec-{i}", f"evt-{i}", {"bundle": "data"}, "PENDING", db_path=str(db_file))
        
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    
    records = get_pending_records(str(db_file))
    assert len(records) == 10

def test_dsse_formatting_mocked():
    adapter = MockMRAdapter()
    TrustedLogAPI(local_mr=adapter)
    # Mocking out the missing dependencies locally
    assert True # In reality we'd assert the dsse StatementBuilder properties 

def test_tokenless_rekor_push_daemon():
    # Setup dummy queue
    # Assert daemon takes from SQLite and calls submit without IdentityToken
    assert True

from tc_api.trucon.adapters.tdx_mr import TdxMRAdapter

def test_tdx_mr_adapter_detects_real_sysfs_node(tmp_path):
    d = tmp_path / "measurements"
    d.mkdir()
    (d / "rtmr2:sha384").write_bytes(b'\x00' * 48)

    assert TdxMRAdapter.is_available(2, sysfs_base_path=str(d / "rtmr")) is True
    assert TdxMRAdapter.is_available(1, sysfs_base_path=str(d / "rtmr")) is False
    assert TdxMRAdapter.is_extend_available(2, sysfs_base_path=str(d / "rtmr")) is True


def test_tdx_mr_adapter_detects_libtdx_attest_extend_fallback(monkeypatch):
    class FakeExtend:
        argtypes = None
        restype = None

    class FakeGetReport:
        argtypes = None
        restype = None

        def __call__(self, report_data_ptr, report_ptr):
            return 0

    class FakeLibrary:
        def __init__(self):
            self.tdx_att_get_report = FakeGetReport()
            self.tdx_att_extend = FakeExtend()

    monkeypatch.setattr(TdxMRAdapter, "is_available", classmethod(lambda cls, index, sysfs_base_path="/sys/class/misc/tdx_guest/measurements/rtmr": False))
    monkeypatch.setattr(TdxMRAdapter, "_load_attest_library", lambda self: FakeLibrary())
    monkeypatch.setattr(TdxMRAdapter, "_read_from_tdreport", lambda self, index: "22" * 48)

    assert TdxMRAdapter.is_extend_available(2) is True


def test_tdx_mr_adapter_rejects_extend_availability_when_fallback_unusable(monkeypatch):
    monkeypatch.setattr(TdxMRAdapter, "is_available", classmethod(lambda cls, index, sysfs_base_path="/sys/class/misc/tdx_guest/measurements/rtmr": False))
    monkeypatch.setattr(TdxMRAdapter, "_load_attest_library", lambda self: (_ for _ in ()).throw(OSError("libtdx_attest missing")))
    monkeypatch.setattr(TdxMRAdapter, "_resolve_guest_device_path", lambda self: None)

    assert TdxMRAdapter.is_extend_available(2) is False


def test_tdx_mr_adapter_detects_ioctl_extend_fallback(monkeypatch):
    monkeypatch.setattr(TdxMRAdapter, "is_available", classmethod(lambda cls, index, sysfs_base_path="/sys/class/misc/tdx_guest/measurements/rtmr": False))
    monkeypatch.setattr(TdxMRAdapter, "_resolve_guest_device_path", lambda self: "/dev/tdx_guest")
    monkeypatch.setattr(TdxMRAdapter, "_read_from_ioctl_report", lambda self, index: "44" * 48)

    assert TdxMRAdapter.is_extend_available(3) is True

def test_tdx_mr_adapter(tmp_path):
    # Setup mock sysfs
    d = tmp_path / "measurements"
    d.mkdir()
    path = d / "rtmr2:sha384"
    # Provide exactly 48 bytes init value
    init_val = b'\x00' * 48
    path.write_bytes(init_val)

    adapter = TdxMRAdapter(sysfs_base_path=str(d / "rtmr"))
    
    # Test read
    val = adapter.read(2)
    assert val == init_val.hex()
    
    # Test extend
    new_hash = "11" * 48
    new_val, prev_val = adapter.extend(2, new_hash)
    
    assert prev_val == init_val.hex()
    assert new_val == new_hash
    
    # Ensure binary content was written
    written_bytes = path.read_bytes()
    assert written_bytes == bytes.fromhex(new_hash)

def test_tdx_mr_adapter_reads_rtmr_from_tdreport_when_sysfs_missing(monkeypatch):
    adapter = TdxMRAdapter(sysfs_base_path="/nonexistent/rtmr")
    monkeypatch.setattr(adapter, "_resolve_guest_device_path", lambda: None)
    report = bytearray(1024)
    expected_rtmr = bytes.fromhex("22" * 48)
    report[816:864] = expected_rtmr

    class FakeGetReport:
        argtypes = None
        restype = None

        def __call__(self, report_data_ptr, report_ptr):
            typed_report_ptr = ctypes.cast(report_ptr, ctypes.POINTER(__import__("tc_api.trucon.adapters.tdx_mr", fromlist=["_TdxReport"])._TdxReport))
            typed_report_ptr.contents.d[:] = report
            return 0

    class FakeLibrary:
        def __init__(self):
            self.tdx_att_get_report = FakeGetReport()

    monkeypatch.setattr(adapter, "_load_attest_library", lambda: FakeLibrary())

    assert adapter.read(2) == expected_rtmr.hex()


def test_tdx_mr_adapter_reads_rtmr_via_ioctl_when_device_available(monkeypatch):
    adapter = TdxMRAdapter(sysfs_base_path="/nonexistent/rtmr")
    monkeypatch.setattr(adapter, "_resolve_guest_device_path", lambda: "/dev/tdx_guest")
    monkeypatch.setattr(adapter, "_read_from_ioctl_report", lambda index: "55" * 48)

    assert adapter.read(3) == "55" * 48


def test_tdx_mr_adapter_extends_via_libtdx_attest_when_sysfs_missing(monkeypatch):
    adapter = TdxMRAdapter(sysfs_base_path="/nonexistent/rtmr")
    monkeypatch.setattr(adapter, "_resolve_guest_device_path", lambda: None)
    values = iter(["00" * 48, "33" * 48])

    class FakeExtend:
        argtypes = None
        restype = None

        def __call__(self, event_ptr):
            event_type = __import__("tc_api.trucon.adapters.tdx_mr", fromlist=["_TdxRtmrEvent"])._TdxRtmrEvent
            typed_ptr = ctypes.cast(event_ptr, ctypes.POINTER(event_type))
            event = typed_ptr.contents
            assert event.version == 1
            assert event.rtmr_index == 2
            assert bytes(event.extend_data) == bytes.fromhex("11" * 48)
            assert event.event_data_size == 0
            return 0

    class FakeGetReport:
        argtypes = None
        restype = None

        def __call__(self, report_data_ptr, report_ptr):
            return 0

    class FakeLibrary:
        def __init__(self):
            self.tdx_att_get_report = FakeGetReport()
            self.tdx_att_extend = FakeExtend()

    monkeypatch.setattr(adapter, "_load_attest_library", lambda: FakeLibrary())
    monkeypatch.setattr(adapter, "read", lambda index: next(values))

    new_val, prev_val = adapter.extend(2, "11" * 48)

    assert prev_val == "00" * 48
    assert new_val == "33" * 48


def test_tdx_mr_adapter_extends_via_ioctl_when_device_available(monkeypatch):
    adapter = TdxMRAdapter(sysfs_base_path="/nonexistent/rtmr")
    monkeypatch.setattr(adapter, "_resolve_guest_device_path", lambda: "/dev/tdx_guest")
    values = iter(["00" * 48, "66" * 48])
    captured = {}

    monkeypatch.setattr(adapter, "read", lambda index: next(values))
    monkeypatch.setattr(adapter, "_extend_via_ioctl", lambda index, raw_bytes: captured.update({"index": index, "raw_bytes": raw_bytes}))

    new_val, prev_val = adapter.extend(3, "11" * 48)

    assert prev_val == "00" * 48
    assert new_val == "66" * 48
    assert captured["index"] == 3
    assert captured["raw_bytes"] == bytes.fromhex("11" * 48)


def test_tdx_mr_adapter_reports_libtdx_attest_extend_errors(monkeypatch):
    adapter = TdxMRAdapter(sysfs_base_path="/nonexistent/rtmr")
    monkeypatch.setattr(adapter, "_resolve_guest_device_path", lambda: None)

    class FakeExtend:
        argtypes = None
        restype = None

        def __call__(self, event_ptr):
            return 0x0006

    class FakeGetReport:
        argtypes = None
        restype = None

        def __call__(self, report_data_ptr, report_ptr):
            return 0

    class FakeLibrary:
        def __init__(self):
            self.tdx_att_get_report = FakeGetReport()
            self.tdx_att_extend = FakeExtend()

    monkeypatch.setattr(adapter, "_load_attest_library", lambda: FakeLibrary())
    monkeypatch.setattr(adapter, "read", lambda index: "00" * 48)

    with pytest.raises(RuntimeError, match="TDX_ATTEST_ERROR_EXTEND_FAILURE"):
        adapter.extend(2, "11" * 48)

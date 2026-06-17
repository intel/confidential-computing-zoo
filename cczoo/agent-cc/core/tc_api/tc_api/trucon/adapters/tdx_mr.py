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

import ctypes
import fcntl
import hashlib
import logging
import os
from ctypes.util import find_library
from typing import Tuple

from tlog.local_mr import LocalMRAdapter

logger = logging.getLogger(__name__)


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


class _TdxReportData(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("d", ctypes.c_uint8 * 64)]


class _TdxReport(ctypes.Structure):
    _pack_ = 1
    _fields_ = [("d", ctypes.c_uint8 * 1024)]


class _TdxRtmrEvent(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("version", ctypes.c_uint32),
        ("rtmr_index", ctypes.c_uint64),
        ("extend_data", ctypes.c_uint8 * 48),
        ("event_type", ctypes.c_uint32),
        ("event_data_size", ctypes.c_uint32),
    ]


class _TdxGuestReportReq(ctypes.Structure):
    _fields_ = [
        ("reportdata", ctypes.c_uint8 * 64),
        ("tdreport", ctypes.c_uint8 * 1024),
    ]


class _TdxGuestExtendRtmrReq(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.c_uint8 * 48),
        ("index", ctypes.c_uint8),
    ]


_TDX_ATTEST_ERROR_NAMES = {
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


def _ioc(direction: int, type_chr: str, number: int, size: int) -> int:
    return (direction << 30) | (ord(type_chr) << 8) | number | (size << 16)


_TDX_CMD_GET_REPORT0 = _ioc(3, "T", 1, ctypes.sizeof(_TdxGuestReportReq))
_TDX_CMD_EXTEND_RTMR = _ioc(2, "T", 3, ctypes.sizeof(_TdxGuestExtendRtmrReq))


class TdxMRAdapter(LocalMRAdapter):
    """
    Adapter for Intel TDX RTMRs via the Linux TDX guest driver's sysfs ABI.

    Userspace does not invoke TDCALL directly. Writing 48 raw digest bytes to
    the RTMR sysfs node delegates the extend operation to the kernel driver,
    which performs the underlying TDG.MR.RTMR.EXTEND call.
    """
    # TDREPORT uses a different layout from the quote body. These offsets were
    # confirmed against real /dev/tdx_guest TDREPORT output and the RTMR values
    # embedded in a quote taken from the same TD state.
    _REPORT_RTMR_OFFSETS = {
        0: 720,
        1: 768,
        2: 816,
        3: 864,
    }

    def __init__(self, sysfs_base_path: str = "/sys/class/misc/tdx_guest/measurements/rtmr"):
        self.sysfs_base_path = sysfs_base_path
        self.attest_library_path = os.environ.get("TRUCON_TDX_ATTEST_LIB", "libtdx_attest.so")
        self.guest_device_path = os.environ.get("TRUCON_TDX_GUEST_DEVICE", "")

    @classmethod
    def is_available(
        cls,
        index: int,
        sysfs_base_path: str = "/sys/class/misc/tdx_guest/measurements/rtmr",
    ) -> bool:
        return os.path.exists(f"{sysfs_base_path}{index}:sha384")

    @classmethod
    def is_report_read_available(cls, index: int) -> bool:
        try:
            adapter = cls()
            if adapter._resolve_guest_device_path() is not None:
                adapter._read_from_ioctl_report(index)
            else:
                adapter._read_from_tdreport(index)
            return True
        except Exception:
            return False

    @classmethod
    def is_extend_available(
        cls,
        index: int,
        sysfs_base_path: str = "/sys/class/misc/tdx_guest/measurements/rtmr",
    ) -> bool:
        if cls.is_available(index, sysfs_base_path=sysfs_base_path):
            return True

        try:
            adapter = cls(sysfs_base_path=sysfs_base_path)
            if adapter._resolve_guest_device_path() is not None:
                adapter._read_from_ioctl_report(index)
                return True
            library = adapter._load_attest_library()
            getattr(library, "tdx_att_extend")
            adapter._read_from_tdreport(index)
            return True
        except Exception:
            return False

    def _get_path(self, index: int) -> str:
        # Expected pattern: /sys/class/misc/tdx_guest/measurements/rtmr0:sha384
        return f"{self.sysfs_base_path}{index}:sha384"

    def _resolve_guest_device_path(self) -> str | None:
        if self.guest_device_path:
            return self.guest_device_path if os.path.exists(self.guest_device_path) else None
        for candidate in ("/dev/tdx_guest", "/dev/tdx-guest"):
            if os.path.exists(candidate):
                return candidate
        return None

    def _open_guest_device(self) -> int:
        device_path = self._resolve_guest_device_path()
        if device_path is None:
            raise FileNotFoundError("No TDX guest ioctl device is available")
        return os.open(device_path, os.O_RDWR)

    def _load_attest_library(self):
        library = _load_tdx_attest_library(self.attest_library_path)
        library.tdx_att_get_report.argtypes = [ctypes.POINTER(_TdxReportData), ctypes.POINTER(_TdxReport)]
        library.tdx_att_get_report.restype = ctypes.c_uint32
        library.tdx_att_extend.argtypes = [ctypes.POINTER(_TdxRtmrEvent)]
        library.tdx_att_extend.restype = ctypes.c_uint32
        return library

    def _extend_via_attest_library(self, index: int, raw_bytes: bytes) -> None:
        library = self._load_attest_library()
        event = _TdxRtmrEvent()
        event.version = 1
        event.rtmr_index = index
        for offset, value in enumerate(raw_bytes):
            event.extend_data[offset] = value
        event.event_type = 0
        event.event_data_size = 0

        error = library.tdx_att_extend(ctypes.byref(event))
        if error != 0:
            error_name = _TDX_ATTEST_ERROR_NAMES.get(error, "TDX_ATTEST_ERROR_UNKNOWN")
            raise RuntimeError(f"libtdx_attest extend failed with code 0x{error:04x} ({error_name})")

    def _read_from_tdreport(self, index: int) -> str:
        offset = self._REPORT_RTMR_OFFSETS.get(index)
        if offset is None:
            raise ValueError(f"TDREPORT RTMR read is unsupported for index {index}")

        library = self._load_attest_library()
        report_data = _TdxReportData()
        report = _TdxReport()
        error = library.tdx_att_get_report(ctypes.byref(report_data), ctypes.byref(report))
        if error != 0:
            raise RuntimeError(f"libtdx_attest get_report failed with code 0x{error:04x}")

        report_bytes = bytes(report.d)
        return report_bytes[offset : offset + 48].hex()

    def _read_from_ioctl_report(self, index: int) -> str:
        offset = self._REPORT_RTMR_OFFSETS.get(index)
        if offset is None:
            raise ValueError(f"TDREPORT RTMR read is unsupported for index {index}")

        fd = self._open_guest_device()
        try:
            request = _TdxGuestReportReq()
            fcntl.ioctl(fd, _TDX_CMD_GET_REPORT0, request, True)
        finally:
            os.close(fd)

        report_bytes = bytes(request.tdreport)
        return report_bytes[offset : offset + 48].hex()

    def _extend_via_ioctl(self, index: int, raw_bytes: bytes) -> None:
        request = _TdxGuestExtendRtmrReq()
        for offset, value in enumerate(raw_bytes):
            request.data[offset] = value
        request.index = index

        fd = self._open_guest_device()
        try:
            fcntl.ioctl(fd, _TDX_CMD_EXTEND_RTMR, request, True)
        finally:
            os.close(fd)

    def read(self, index: int) -> str:
        path = self._get_path(index)
        if not os.path.exists(path):
            if self._resolve_guest_device_path() is not None:
                return self._read_from_ioctl_report(index)
            return self._read_from_tdreport(index)
            
        try:
            with open(path, "rb") as f:
                return f.read().hex()
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to read TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error reading from {path}: {e}")
            raise

    def extend(self, index: int, digest: str) -> Tuple[str, str]:
        # Strip potential known prefixes
        if digest.startswith("sha384:"):
            digest = digest[7:]
            
        path = self._get_path(index)
        try:
            prev_val = self.read(index)
            
            # Convert string to exactly 48 bytes
            try:
                raw_bytes = bytes.fromhex(digest)
            except ValueError:
                raise ValueError(f"Provided digest is not a valid hex string: {digest}")
                
            if len(raw_bytes) != 48:
                raise ValueError(f"TDX RTMR requires exactly 48 bytes (sha384), but got {len(raw_bytes)}")

            if os.path.exists(path):
                # The kernel driver's sysfs write handler performs the real RTMR extend.
                with open(path, "rb+") as f:
                    f.write(raw_bytes)
            elif self._resolve_guest_device_path() is not None:
                self._extend_via_ioctl(index, raw_bytes)
            else:
                self._extend_via_attest_library(index, raw_bytes)
                
            new_val = self.read(index)
            return (new_val, prev_val)
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to extend TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error extending {path} with digest {digest}: {e}")
            raise

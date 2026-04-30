import ctypes
import hashlib
import logging
import os
from typing import Tuple

from tc_api.tlog.local_mr import LocalMRAdapter

logger = logging.getLogger(__name__)


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


class TdxMRAdapter(LocalMRAdapter):
    """
    Adapter for Intel TDX RTMRs via the Linux TDX guest driver's sysfs ABI.

    Userspace does not invoke TDCALL directly. Writing 48 raw digest bytes to
    the RTMR sysfs node delegates the extend operation to the kernel driver,
    which performs the underlying TDG.MR.RTMR.EXTEND call.
    """
    _REPORT_RTMR_OFFSETS = {
        0: 192,
        1: 240,
        2: 288,
        3: 336,
    }

    def __init__(self, sysfs_base_path: str = "/sys/class/misc/tdx_guest/measurements/rtmr"):
        self.sysfs_base_path = sysfs_base_path
        self.attest_library_path = os.environ.get("TRUCON_TDX_ATTEST_LIB", "libtdx_attest.so")

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
            cls()._read_from_tdreport(index)
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
            library = adapter._load_attest_library()
            getattr(library, "tdx_att_extend")
            adapter._read_from_tdreport(index)
            return True
        except Exception:
            return False

    def _get_path(self, index: int) -> str:
        # Expected pattern: /sys/class/misc/tdx_guest/measurements/rtmr0:sha384
        return f"{self.sysfs_base_path}{index}:sha384"

    def _load_attest_library(self):
        library = ctypes.CDLL(self.attest_library_path)
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

    def read(self, index: int) -> str:
        path = self._get_path(index)
        if not os.path.exists(path):
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
            else:
                self._extend_via_attest_library(index, raw_bytes)
                
            new_val = self.read(index)
            return (new_val, prev_val)
        except PermissionError:
            raise PermissionError(f"Insufficient permissions to extend TDX RTMR sysfs at {path}")
        except Exception as e:
            logger.error(f"Error extending {path} with digest {digest}: {e}")
            raise

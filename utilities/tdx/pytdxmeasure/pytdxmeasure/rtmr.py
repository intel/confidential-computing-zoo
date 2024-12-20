"""
RTMR data structures
"""

import os
import fcntl
import struct
import logging
from .binaryblob import BinaryBlob

__author__ = 'cpio'
LOG = logging.getLogger(__name__)

class RTMR(BinaryBlob):
    """
    Data structure for RTMR registers.
    A RTMR register manages a 48-bytes (384-bits) hash value.
    """
    RTMR_COUNT = 4
    RTMR_LENGTH_BY_BYTES = 48
    TDX_ATTEST_FILE = '/dev/tdx_guest'
    EXTEND_SUCCESS = 'RTMR_EXTEND_SUCCESS'
    EXTEND_FAILURE = 'RTMR_EXTEND_FAILURE'
    EXTEND_FAILURE_WITH_WRONG_INPUT = 'RTMR_EXTEND_FAILURE_WITH_WRONG_INPUT'

    def __init__(self, data: bytearray = bytearray(RTMR_LENGTH_BY_BYTES),
        base_addr=0):
        super().__init__(data, base_addr)

    def __eq__(self, other):
        bytearray_1, _ = self.get_bytes(0, RTMR.RTMR_LENGTH_BY_BYTES)
        bytearray_2, _ = other.get_bytes(0, RTMR.RTMR_LENGTH_BY_BYTES)

        return bytearray(bytearray_1) == bytearray(bytearray_2)

    @staticmethod
    def extend_rtmr(raw_extend_data, extend_rtmr_index):
        """
        Perform ioctl on the device file /dev/tdx_guest to extend rtmr
        """
        if not os.path.exists(RTMR.TDX_ATTEST_FILE):
            LOG.error("Could not find device node %s. Kernel version 6.2 above supports RTMR write",
                      RTMR.TDX_ATTEST_FILE)
            return None

        try:
            fd_tdx_attest = os.open(RTMR.TDX_ATTEST_FILE, os.O_RDWR)
        except (PermissionError, IOError, OSError):
            LOG.error("Fail to open file %s", RTMR.TDX_ATTEST_FILE)
            return None

        #Perform extend through ioctl call
        #Reference: Structure of tdx_extend_rtmr_req in /include/uapi/linux/tdx-guest.h
        #struct tdx_extend_rtmr_req {
        #    __u8 data[TDX_EXTEND_RTMR_DATA_LEN];
        #    __u8 index;
        #};

        extend_data = bytearray(raw_extend_data.encode())
        if len(extend_data) != RTMR.RTMR_LENGTH_BY_BYTES:
            LOG.error("Invalid length for the extend data. Should be 48B length.")
            return RTMR.EXTEND_FAILURE_WITH_WRONG_INPUT

        req = struct.pack("@48sB", extend_data, int(extend_rtmr_index))

        #Reference: command used for tdx rtmr extend defined in /include/uapi/linux/tdx-guest.h
        #define TDX_CMD_EXTEND_RTMR		_IOR('T', 3, struct tdx_extend_rtmr_req)
        try:
            fcntl.ioctl(fd_tdx_attest,
                        int.from_bytes(struct.pack('Hcb', 0x3180, b'T', 3), 'big'), req)
        except OSError:
            LOG.info("Fail to execute ioctl for file %s", RTMR.TDX_ATTEST_FILE)
            os.close(fd_tdx_attest)
            return RTMR.EXTEND_FAILURE

        os.close(fd_tdx_attest)
        LOG.info("RTMR extend success.")
        return RTMR.EXTEND_SUCCESS

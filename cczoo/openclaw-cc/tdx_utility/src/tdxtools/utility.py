'''
Module utility provides constant variables defined in outer
references and helper classes.
'''
import os
import logging
import ctypes
import struct
import fcntl
from typing import List

__author__ = "cpio"

LOG = logging.getLogger(__name__)

# The name of the device in different kernel version
DEVICE_NODE_NAME_DEPRECATED = "/dev/tdx-attest"   # deprecated
DEVICE_NODE_NAME_1_0 = "/dev/tdx-guest"
DEVICE_NODE_NAME_1_5 = "/dev/tdx_guest"

# The device operators for tdx v1.0
#
# Reference: TDX_CMD_GET_REPORT
# defined in arch/x86/include/uapi/asm/tdx.h in kernel source
# Layout: dir(2bit) size(14bit)         type(8bit) nr(8bit)
#         11        00,0000,0000,1000   b'T'       0000,0001
# The higher 16bit is standed by 0xc008 in big-endian,
# 0x08c0 in little-endian.
TDX_CMD_GET_REPORT_V1_0 = int.from_bytes(struct.pack('Hcb', 0x08c0, b'T', 1), 'big')

# The devic operators for tdx v1.5
# Reference: TDX_CMD_GET_REPORT0
# defined in include/uapi/linux/tdx-guest.h in kernel source
# Layout: dir(2bit) size(14bit)         type(8bit) nr(8bit)
#         11        00,0100,0100,0000   b'T'       0000,0001
# The higher 16bit is standed by 0xc440 in big-endian,
# 0x40c4 in little-endian.
TDX_CMD_GET_REPORT0_V1_5 = int.from_bytes(struct.pack('Hcb', 0x40c4, b'T', 1),'big')

# The valid value of tcb_info_valid
# Note:
# 1.  In tdx 1.0, the valid(8 bytes), tee_tcb_svn(16 bytes), mrseam(48 bytes) are
#     ready. The valid structure can be written in little-endian as
#     '1111,1111 1000,0000 0..0', transformed to '1111,1111 0000,0001 0..0' or
#     '0xff 01 0..0' in human-readable format.
# 2.  In tdx 1.5, tee_tcb_svn2(16 bytes) is introdued and placed the previously
#     reserved section closet to the attributes structure. The valid structure is
#     written as '1111,1111 1000,0000 1100,0000 0..0' in little-enditan, or
#     '1111,1111 0000,0001 0000,0011 0..0' or '0xff 01 03 0..0' in human-readable
#     format.
# Ref: Intel® CPU Architectural Extensions Specification
# in https://www.intel.com/content/www/us/en/developer/articles/technical
# /intel-trust-domain-extensions.html
# FIXME: tee_tcb_svn2 info update # pylint: disable=fixme
TCB_INFO_VALID_VAL_1_0 =  b"\xff\x01\x00\x00\x00\x00\x00\x00"
TCB_INFO_VALID_VAL_1_5 = b"\xff\x01\x03\x00\x00\x00\x00\x00"

# The length of the reportdata
TDX_REPORTDATA_LEN = 64
# The length of the tdreport
TDX_REPORT_LEN = 1024

class DeviceNode:
    """
    DeviceNode manager operation on tdx device in guest
    Support devices:
    * DEVICE_NODE_NAME_1_0
    * DEVICE_NODE_NAME_1_5
    Support operation:
    * GET_TDREPORT
    """
    GET_TDREPORT = "get tdreport"

    class DeviceOperatorsMap:
        '''
        Class DeviceOperatorsMap contains the name of a device node
        and corresponding opertors on it.
        '''
        def __init__(self, device:str, operators: map):
            self.device_node = device
            self.operators = operators

    DEVICE_OPERATOR_MAPS = [
        DeviceOperatorsMap(DEVICE_NODE_NAME_1_0, {
            GET_TDREPORT: TDX_CMD_GET_REPORT_V1_0}),
        DeviceOperatorsMap(DEVICE_NODE_NAME_1_5, {
            GET_TDREPORT: TDX_CMD_GET_REPORT0_V1_5})
    ]

    def __init__(self):
        self.device_node_name = None
        self.operators = None
        self._determine_device_node()

    def _determine_device_node(self):
        if os.path.exists(DEVICE_NODE_NAME_DEPRECATED):
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEVICE_NODE_NAME_DEPRECATED, DEVICE_NODE_NAME_1_0, DEVICE_NODE_NAME_1_5)
            return

        for dom in self.DEVICE_OPERATOR_MAPS:
            if  os.path.exists(dom.device_node):
                self.device_node_name = dom.device_node
                self.operators = dom.operators
                break

        if self.device_node_name is None:
            for dom in self.DEVICE_OPERATOR_MAPS:
                if  os.path.exists(dom.device_node):
                    self.device_node_name = dom.device_node
                    self.operators = dom.operators
                    break

    def get_tdreport_bytes(self, report_data=None):
        '''
        Method get_tdreport_bytes requests the tdx device to retrive
        the tdreport in bytes format.
        '''
        if self.device_node_name is None or self.operators is None:
            LOG.error("Invalid device node: %s", self.device_node_name)
            return None

        # 1. Get the operator
        operator = self.operators[self.GET_TDREPORT]
        if operator is None:
            LOG.error("Device %s not support operation %s",
                      self.device_node_name, self.GET_TDREPORT)
            return None

        # 2. Get device file descriptor
        try:
            fd_tdx_device = os.open(self.device_node_name, os.O_RDWR)
        except (PermissionError, IOError, OSError):
            LOG.error("Fail to open file %s", self.device_node_name)
            return None

        # 3. Create the request
        req = self.create_tdx_report_req(report_data)

        # 4. Retrieve tdreport
        try:
            fcntl.ioctl(fd_tdx_device,
                operator,
                req)
        except OSError:
            LOG.error("Fail to execute ioctl for file %s", self.device_node_name)
            os.close(fd_tdx_device)
            return None
        os.close(fd_tdx_device)

        # 5. Get tdreport bytes form tdx_report_req
        tdreport_bytes = self.get_tdreport_bytes_from_req(req)
        return tdreport_bytes

    def create_tdx_report_req(self, report_data=None):
        '''
        Method create_tdx_report_req creates a tdx_report_req struct
        with report_data.
        '''
        length = 0
        if  report_data is not None:
            length = len(report_data)
        if length > TDX_REPORTDATA_LEN:
            LOG.error("Input report_data is longer than TDX_REPORTDATA_LEN")
            return None

        if self.device_node_name == DEVICE_NODE_NAME_1_0:
            reportdata = ctypes.create_string_buffer(TDX_REPORTDATA_LEN)
            for index in range(length):
                reportdata[index] = report_data[index]
            tdreport = ctypes.create_string_buffer(TDX_REPORT_LEN)
            req = struct.pack("BQLQL", 0, ctypes.addressof(reportdata), TDX_REPORTDATA_LEN,
                    ctypes.addressof(tdreport), TDX_REPORT_LEN)
            return req

        if self.device_node_name == DEVICE_NODE_NAME_1_5:
            req = bytearray(TDX_REPORTDATA_LEN + TDX_REPORT_LEN)
            for index in range(length):
                req[index] = report_data[index]
            return req
        return None

    def get_tdreport_bytes_from_req(self, req):
        '''
        Method get_tdreport_bytes_from_req retrieves the tdreprot in bytes
        format from the tdx_report_req struct.
        '''
        if self.device_node_name == DEVICE_NODE_NAME_1_0:
            parts = struct.unpack("BQLQL", req)
            buffer = (ctypes.c_char * TDX_REPORT_LEN).from_address(parts[3])
            return bytearray(buffer)
        if self.device_node_name == DEVICE_NODE_NAME_1_5:
            tdreport_bytes = req[TDX_REPORTDATA_LEN:]
            return tdreport_bytes
        return None

    def get_tee_tcb_info_valid_val(self):
        '''
        Method get_tee_tcb_info_valid_val helps get the valid value
        of the field tdreport.tee_tcb_info.valid.
        '''
        val = b"\x00"
        if self.device_node_name == DEVICE_NODE_NAME_DEPRECATED:
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEVICE_NODE_NAME_DEPRECATED, DEVICE_NODE_NAME_1_0, DEVICE_NODE_NAME_1_5)
        elif self.device_node_name == DEVICE_NODE_NAME_1_0:
            val = TCB_INFO_VALID_VAL_1_0
        elif self.device_node_name == DEVICE_NODE_NAME_1_5:
            val = TCB_INFO_VALID_VAL_1_5
        return val

class ModuleVersion:
    '''
    class ModuleVersion contains version infomation of tdx module
    '''

    VALID_SVN_LENGTH = 16

    def __init__(self, release_names: List[str], major: int, minor: int, is_debug: bool = False):
        self.release_names = release_names
        self.major = major
        self.minor = minor
        self.is_debug = is_debug

    @staticmethod
    def from_bytes(tee_tcb_svn: bytes):
        '''
        Method from_bytes parses bytes of the svn, if it
        is valid, return the instance of the module version.
        '''
        if len(tee_tcb_svn) != ModuleVersion.VALID_SVN_LENGTH:
            return None, False
        version_bytes = tee_tcb_svn[0:2]
        for version in VALID_MODULE_VERSIONS:
            if version.to_hex().to_bytes(2, byteorder='little') == version_bytes:
                return version, True
        return None, False

    def to_hex(self):
        '''
        Method to_hex converts the module version to the svn in hex.
        '''
        return self.major * 16 * 16 + self.minor

    def __str__(self):
        sep = " or "
        names = sep.join(self.release_names)
        return (f'module version: {{ '
                f'release_names: {names},'
                f'major: {self.major},'
                f'minor: {self.minor},'
                f'is_debug: {self.is_debug}'
                f' }}'
               )

VALID_MODULE_VERSIONS = [
    ModuleVersion(["1.0"], 0, 0, True),
    ModuleVersion(["1.0"], 0, 3),
    ModuleVersion(["1.4", "1.5"], 1, 0, True),
    ModuleVersion(["1.4", "1.5"], 1, 3),
    ModuleVersion(["2.0"], 2, 0, True),
    ModuleVersion(["2.0"], 2, 3),
]

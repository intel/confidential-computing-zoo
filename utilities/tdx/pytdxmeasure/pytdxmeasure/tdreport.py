"""
Parse td report struct, see:
https://software.intel.com/content/dam/develop/external/us/en/documents/tdx-module-1eas-v0.85.039.pdf  # pylint: disable=line-too-long
https://software.intel.com/content/dam/develop/external/us/en/documents-tps/intel-tdx-cpu-architectural-specification.pdf  # pylint: disable=line-too-long
"""

import logging

from .utility import DeviceNode, \
        DEVICE_NODE_NAME_DEPRECATED as DEV_DEPRECATED, \
        DEVICE_NODE_NAME_1_0 as DEV_1_0, \
        DEVICE_NODE_NAME_1_5 as DEV_1_5
from .binaryblob import BinaryBlob

__author__ = "cpio"

LOG = logging.getLogger(__name__)


class ReportMacStruct(BinaryBlob):
    """
    Struct REPORTMACSTRUCT
    """

    def __init__(self, data):
        super().__init__(data)
        self.report_type = None
        self.reserverd1 = None
        self.cpusvn = None
        self.tee_tcb_info_hash = None
        self.tee_info_hash = None
        self.report_data = None
        self.reserverd2 = None
        self.mac = None
        self.parse()

    def parse(self):
        """
        parse the raw data for Struct REPORTMACSTRUCT

        Struct REPORTMACSTRUCT's layout:
        offset, len
        0x0,    0x8     report_type
        0x8,    0x8     reserverd1
        0x10,   0x10    cpusvn
        0x20,   0x30    tee_tcb_info_hash
        0x50,   0x30    tee_info_hash
        0x80,   0x40    report_data
        0xc0,   0x20    reserverd2
        0xe0,   0x20    mac
        """
        offset = 0

        self.report_type, offset = self.get_bytes(offset, 0x8)
        self.reserverd1, offset = self.get_bytes(offset, 0x8)
        self.cpusvn, offset = self.get_bytes(offset, 0x10)
        self.tee_tcb_info_hash, offset = self.get_bytes(offset, 0x30)
        self.tee_info_hash, offset = self.get_bytes(offset, 0x30)
        self.report_data, offset = self.get_bytes(offset, 0x40)
        self.reserverd2, offset = self.get_bytes(offset, 0x20)
        self.mac, offset = self.get_bytes(offset, 0x20)

class TeeTcbInfo(BinaryBlob):
    """
    Struct TEE_TCB_INFO
    """

    def __init__(self, data, device):
        super().__init__(data)
        # auxiliary fileds
        self.device = device
        # real fields
        self.valid = None
        self.tee_tcb_svn = None
        self.mrseam = None
        self.mrsignerseam = None
        self.attributes = None
        self.tee_tcb_svn2 = None
        self.reserved = None
        self.parse()

    def parse(self):
        """
        parse the raw data for Struct TEE_TCB_INFO

        Struct TEE_TCB_INFO's layout:
        offset, len
        0x0,    0x08    valid
        0x8,    0x10    tee_tcb_svn
        0x18,   0x30    mrseam
        0x48,   0x30    mrsignerseam
        0x78,   0x08    attributes

        # fileds in tdx v1.0
        0x80,   0x6f    reserved

        # fileds in tdx v1.5
        0x80,   0x10    tee_tcb_svn2
        0x90,   0x5f    reserved

        FIXME:  need spec reference to update info # pylint: disable=fixme
                about new field tee_tcb_svn2
        """
        if self.device == DEV_DEPRECATED:
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEV_DEPRECATED, DEV_1_0, DEV_1_5)
            return

        offset = 0

        self.valid, offset = self.get_bytes(offset, 0x8)
        self.tee_tcb_svn, offset = self.get_bytes(offset, 0x10)
        self.mrseam, offset = self.get_bytes(offset, 0x30)
        self.mrsignerseam, offset = self.get_bytes(offset, 0x30)
        self.attributes, offset = self.get_bytes(offset, 0x8)

        if  self.device == DEV_1_0:
            self.reserved, offset = self.get_bytes(offset, 0x6f)
        elif self.device == DEV_1_5:
            self.tee_tcb_svn2, offset = self.get_bytes(offset, 0x10)
            self.reserved, offset = self.get_bytes(offset, 0x5f)

class TdInfo(BinaryBlob):
    """
    Struct TDINFO_STRUCT
    """

    def __init__(self, data, device):
        super().__init__(data)
        # auxiliary fileds
        self.device = device
        # read fields
        self.attributes = None
        self.xfam = None
        self.mrtd = None
        self.mrconfigid = None
        self.mrowner = None
        self.mrownerconfig = None
        self.rtmr_0 = None
        self.rtmr_1 = None
        self.rtmr_2 = None
        self.rtmr_3 = None
        self.servtd_hash = None
        self.reserved = None
        self.parse()

    def parse(self):
        '''
        parse the raw data for Struct TDINFO_STRUCT

        Struct TDINFO_STRUCT's layout:
        offset, len
        0x0,    0x8     attributes
        0x8,    0x8     xfam
        0x10,   0x30    mrtd
        0x40,   0x30    mrconfigid
        0x70,   0x30    mrowner
        0xa0,   0x30    mrownerconfig
        0xd0,   0x30    rtmr_0
        0x100,  0x30    rtmr_1
        0x130,  0x30    rtmr_2
        0x160,  0x30    rtmr_3

        # fields in tdx v1.0
        0x190,  0x70    reserved

        # fields in tdx v1.5
        0x190,  0x30    servtd_hash
        0x1c0,  0x40    reserved

        ref:
            Page 40 of Intel® TDX Module v1.5 ABI Specification
            from https://www.intel.com/content/www/us/en/developer/articles/technical/
            intel-trust-domain-extensions.html
        '''

        if self.device == DEV_DEPRECATED:
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEV_DEPRECATED, DEV_1_0, DEV_1_5)
            return

        offset = 0

        self.attributes, offset = self.get_bytes(offset, 0x8)
        self.xfam, offset = self.get_bytes(offset, 0x8)
        self.mrtd, offset = self.get_bytes(offset, 0x30)
        self.mrconfigid, offset = self.get_bytes(offset, 0x30)
        self.mrowner, offset = self.get_bytes(offset, 0x30)
        self.mrownerconfig, offset = self.get_bytes(offset, 0x30)
        self.rtmr_0, offset = self.get_bytes(offset, 0x30)
        self.rtmr_1, offset = self.get_bytes(offset, 0x30)
        self.rtmr_2, offset = self.get_bytes(offset, 0x30)
        self.rtmr_3, offset = self.get_bytes(offset, 0x30)

        if  self.device == DEV_1_0:
            self.reserved, offset = self.get_bytes(offset, 0x70)
        elif self.device == DEV_1_5:
            self.servtd_hash, offset = self.get_bytes(offset, 0x30)
            self.reserved, offset = self.get_bytes(offset, 0x40)

class TdReport(BinaryBlob):
    """
    Struct TDREPORT_STRUCT
    """
    def __init__(self, data, device_node=None):
        super().__init__(data)
        # auxiliary fileds
        if device_node is None:
            device_node = DeviceNode()
        self.device_node = device_node
        # real fields in TDREPORT_STRUCT
        self.report_mac_struct = None
        self.tee_tcb_info = None
        self.reserved = None
        self.td_info = None
        self.parse()

    def parse(self):
        '''
        parse the raw data for Struct TDREPORT_STRUCT

        Struct TDREPORT_STRUCT's layout:
        offset, len
        0x0,    0x100   ReportMacStruct
        0x100,  0xef    TeeTcbInfo
        0x1ef,  0x11    Reserved
        0x200,  0x200   TdInfo
        '''
        if self.device_node == DEV_DEPRECATED:
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEV_DEPRECATED, DEV_1_0, DEV_1_5)
            return

        offset = 0

        data, offset = self.get_bytes(offset, 0x100)
        self.report_mac_struct = ReportMacStruct(data)

        data, offset = self.get_bytes(offset, 0xef)
        self.tee_tcb_info = TeeTcbInfo(data, self.device_node.device_node_name)

        data, offset = self.get_bytes(offset, 0x11)
        self.reserved = data

        data, offset = self.get_bytes(offset, 0x200)
        self.td_info = TdInfo(data, self.device_node.device_node_name)

    @staticmethod
    def get_td_report(report_data=None):
        """
        Perform ioctl on the device file, to get td-report
        """
        device_node = DeviceNode()
        tdreport_bytes = device_node.get_tdreport_bytes(report_data)
        report = TdReport(tdreport_bytes, device_node)
        return report

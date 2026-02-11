#!/usr/bin/env python3
#
# Copyright 2024 Canonical Ltd.
# Authors:
# - Hector Cao <hector.cao@canonical.com>
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranties of MERCHANTABILITY,
# SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License along with
# this program.  If not, see <http://www.gnu.org/licenses/>.
#

import logging
import json
import binascii
import re

from .utility import DeviceNode, \
        DEVICE_NODE_NAME_DEPRECATED as DEV_DEPRECATED, \
        DEVICE_NODE_NAME_1_0 as DEV_1_0, \
        DEVICE_NODE_NAME_1_5 as DEV_1_5
from .utility import ModuleVersion

from .binaryblob import BinaryBlob

LOG = logging.getLogger(__name__)

class ReportType_Type():
    REPORTTYPE_TYPE_SGX = 0x00
    REPORTTYPE_TYPE_TDX = 0x81

class ReportType(BinaryBlob,dict):
    """
    """
    def __init__(self, data):
        super().__init__(data)
        self.parse()

    def parse(self):
        offset = 0
        val, offset = self.get_uint8(offset)
        self.__setitem__('type', val)
        val, offset = self.get_uint8(offset)
        self.__setitem__('subtype', val)
        version, offset = self.get_uint8(offset)
        self.__setitem__('version', val)
        val, _ = self.get_uint8(offset)
        self.__setitem__('reserved', val)

class ReportMacStruct(BinaryBlob, dict):
    """
    Struct REPORTMACSTRUCT
    """

    def __init__(self, data):
        super().__init__(data)
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

        data, offset = self.get_bytes(offset, 0x8)
        self.__setitem__('report_type', ReportType(data))
        val, offset = self.get_as_hex_string(offset, 0x8)
        self.__setitem__('reserved1', val)
        val, offset = self.get_as_hex_string(offset, 0x10)
        self.__setitem__('cpusvn', val)
        val, offset = self.get_as_hex_string(offset, 0x30)
        self.__setitem__('tee_tcb_info_hash', val)
        val, offset = self.get_as_hex_string(offset, 0x30)
        self.__setitem__('tee_info_hash', val)
        val, offset = self.get_as_hex_string(offset, 0x40)
        self.__setitem__('report_data', val)
        val, offset = self.get_as_hex_string(offset, 0x20)
        self.__setitem__('reserved2', val)
        val, offset = self.get_as_hex_string(offset, 0x20)
        self.__setitem__('mac', val)

class TeeTcbInfo(BinaryBlob, dict):
    """
    Struct TEE_TCB_INFO
    """

    def __init__(self, data, device):
        super().__init__(data)
        # auxiliary fields
        self.device = device
        self.module_version = None

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
        0x78,   0x08    attributes (set to all 0's)

        # fields in tdx v1.0
        0x80,   0x6f    reserved

        # fields in tdx v1.5
        0x80,   0x10    tee_tcb_svn2
        0x90,   0x5f    reserved
        """
        if self.device == DEV_DEPRECATED:
            LOG.error("Deprecated device node %s, please upgrade to use %s or %s",
                      DEV_DEPRECATED, DEV_1_0, DEV_1_5)
            return

        offset = 0

        val, offset = self.get_as_hex_string(offset, 0x8)
        self.__setitem__('valid', val)
        val, offset = self.get_as_hex_string(offset, 0x10)
        self.__setitem__('tee_tcb_svn', val)
        val, offset = self.get_as_hex_string(offset, 0x30)
        self.__setitem__('mrseam', val)
        val, offset = self.get_as_hex_string(offset, 0x30)
        self.__setitem__('mrsignerseam', val)
        val, offset = self.get_as_hex_string(offset, 0x8)
        self.__setitem__('attributes', val)

        if  self.device == DEV_1_0:
            val, offset = self.get_as_hex_string(offset, 0x6f)
            self.__setitem__('reserved', val)
        elif self.device == DEV_1_5:
            val, offset = self.get_as_hex_string(offset, 0x10)
            self.__setitem__('tee_tcb_svn2', val)
            val, offset = self.get_as_hex_string(offset, 0x5f)
            self.__setitem__('reserved', val)

        # parse module svn
        self.module_version, _ = ModuleVersion.from_bytes(self.__getitem__('tee_tcb_svn'))

class TdInfo(BinaryBlob, dict):
    """
    Struct TDINFO_STRUCT
    """


    def __init__(self, data, device):
        super().__init__(data)
        # auxiliary fileds
        self.device = device
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

        _fields_ = [
            ('attributes',    0x8),
            ('xfam',          0x8),
            ('mrtd',          0x30),
            ('mrconfigid',    0x30),
            ('mrowner',       0x30),
            ('mrownerconfig', 0x30),
            ('rtmr_0',        0x30),
            ('rtmr_1',        0x30),
            ('rtmr_2',        0x30),
            ('rtmr_3',        0x30)]

        offset = 0
        for (name, valsize) in _fields_:
            val, offset = self.get_as_hex_string(offset, valsize)
            self.__setitem__(name, val)

        if  self.device == DEV_1_0:
            val, offset = self.get_as_hex_string(offset, 0x70)
            self.__setitem__('reserved', val)
        elif self.device == DEV_1_5:
            val, offset = self.get_as_hex_string(offset, 0x30)
            self.__setitem__('servtd_hash', val)
            val, offset = self.get_as_hex_string(offset, 0x40)
            self.__setitem__('reserved', val)

class TdReport(BinaryBlob, dict):
    """
    Struct TDREPORT_STRUCT
    Details can be found in : Architecture Specification : Intel Trust Domain Extension Module
    Section 22.6 : Measurement and attestation types
    The report structure is essentially composed of 3 sub-structures
      - MACSTRUCT : contains information of the hardware (CPUSVN) and SHA348 hashes
        of the remainder of the report structure (TEE_TCB_INFO and TDINFO)
      - TEE_TCB_INFO : this is report data related to the TEE, it contains
        the measurements of the TDX module
      - TDINFO : this is report data specific to the TD
    """
    def __init__(self, data, device_node=None):
        super().__init__(data)
        # auxiliary fileds
        if device_node is None:
            device_node = DeviceNode()
        self.device_node = device_node
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
        self.__setitem__('report_mac_struct', ReportMacStruct(data))

        data, offset = self.get_bytes(offset, 0xef)
        val = TeeTcbInfo(data, self.device_node.device_node_name)
        self.__setitem__('tee_tcb_info', val)

        val, offset = self.get_as_hex_string(offset, 0x11)
        self.__setitem__('reserved', val)

        data, offset = self.get_bytes(offset, 0x200)
        val = TdInfo(data, self.device_node.device_node_name)
        self.__setitem__('td_info', val)

    def __str__(self):
        return json.dumps(self, indent=2)

    @staticmethod
    def get_td_report(report_data=None):
        """
        Perform ioctl on the device file, to get td-report
        """
        device_node = DeviceNode()
        tdreport_bytes = device_node.get_tdreport_bytes(report_data)
        report = TdReport(tdreport_bytes, device_node)
        return report

    def get_rtmrs(self):
        """
        Get RTMRs
        """
        rtmrs = {}
        for key,value in self['td_info'].items():
            if re.match('rtmr_[0-9]+', key):
                rtmrs[key] = value
        return rtmrs

def main():
    logging.basicConfig(level=logging.DEBUG, format='%(message)s')
    LOG.info("%s", TdReport.get_td_report())

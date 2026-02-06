""" CCEL ACPI table for TDX Event Log.

see https://software.intel.com/content/dam/develop/external/us/en/documents/intel-tdx-guest-hypervisor-communication-interface.pdf> # pylint: disable=line-too-long

"""

import os
import logging

from .binaryblob import BinaryBlob

__author__ = "cpio"

LOG = logging.getLogger(__name__)

class CCEL(BinaryBlob, dict):
    """
    The Confidential Computing Event Log (CCEL) table provides the address
    and length of the CCEL records area in UEFI reserved memory. To access
    these records, userspace can use /dev/mem to retrieve them. But
    '/dev/mem' is not enabled on many systems for security reasons.

    So to allow user space access these event log records without the
    /dev/mem interface, add support to access it via sysfs interface. The
    ACPI driver has provided read only access to BERT records area via
    '/sys/firmware/acpi/tables/data/BERT' in sysfs. So follow the same way,
    and add support for /sys/firmware/acpi/tables/data/CCEL to enable
    read-only access to the CCEL records area.

    More details about the CCEL table can be found in ACPI specification
    r6.5, sec titled "CC Event Log ACPI Table".
    """

    def __init__(self, data):
        super().__init__(data)
        self.parse()

    def parse(self):
        self.__setitem__('length', self.length)
        self.__setitem__('checksum', self.checksum)
        self.__setitem__('revision', self.revision)
        self.__setitem__('checksum', self.checksum)
        self.__setitem__('oem_id', self.oem_id)
        self.__setitem__('cc_type', self.cc_type)
        self.__setitem__('cc_subtype', self.cc_subtype)
        # UEFI memory region start that contains the event log table
        self.__setitem__('log_start_addr', hex(self.log_area_start_address))
        self.__setitem__('log_min_len', self.log_area_minimum_length)

    @property
    def revision(self):
        """
        Revision value in integer
        """
        revision, _ = self.get_uint8(8)
        return revision

    @property
    def checksum(self):
        """
        Checksum value in integer
        """
        checksum, _ = self.get_uint8(9)
        return checksum

    @property
    def oem_id(self):
        """
        OEM ID value in byte array
        """
        oem_id, _ = self.get_bytes(10, 6)
        return oem_id

    @property
    def cc_type(self):
        """
        Confidential Computing type in integer
        """
        cc_type, _ = self.get_uint8(36)
        return cc_type

    @property
    def cc_subtype(self):
        """
        Confidential Computing specific sub-type in integer
        """
        cc_subtype, _ = self.get_uint8(37)
        return cc_subtype

    @property
    def log_area_minimum_length(self):
        """
        LAML value in integer
        """
        laml, _ = self.get_uint64(40)
        return laml

    @property
    def log_area_start_address(self):
        """
        LASA value in integer
        """
        lasa, _ = self.get_uint64(48)
        return lasa

    def dump(self):
        """
        Dump the full information
        """
        super().dump()

        if not self.is_valid():
            LOG.error("CCEL is not valid")
            return

        LOG.info("Revision:     %d", self.revision)
        LOG.info("Length:       %d", self.length)
        LOG.info("Checksum:     %02X", self.checksum)
        LOG.info("OEM ID:       %s", self.oem_id)
        LOG.info("CC Type:      %s", self.cc_type)
        LOG.info("CC Sub-type:  %s", self.cc_subtype)
        LOG.info("Log Lenght:   0x%08X", self.log_area_minimum_length)
        LOG.info("Log Address:  0x%08X", self.log_area_start_address)

    def is_valid(self):
        """
        Judge whether the CCEL data is valid.
        - Check the signature
        - Check the length
        """
        return self.length > 0 and \
            self.data[0:4] == b'CCEL' and \
            self.length == self.data[4]

    @staticmethod
    def create_from_acpi_file(acpi_file="/sys/firmware/acpi/tables/CCEL"):
        """
        Read the CCEL table from the /sys/firmware/acpi/tables/CCEL
        """
        if not os.path.exists(acpi_file):
            LOG.error("Could not find the ACPI file %s", acpi_file)
            return None

        try:
            with open(acpi_file, "rb") as fobj:
                data = fobj.read()
                assert len(data) > 0 and data[0:4] == b'CCEL', \
                    "Invalid CCEL table"
                return CCEL(data)
        except (PermissionError, OSError):
            LOG.error("Need root permission to open file %s", acpi_file)
            return None

"""
TD Event log package.
"""

import logging
from typing import List

from .binaryblob import BinaryBlob

__author__ = "cpio"

LOG = logging.getLogger(__name__)


# pylint: disable=too-few-public-methods
class TDEventLogType:
    """
    Log event types. These are spread out over 2 specs:
    "TCG EFI Protocol Specification For TPM Family 1.1 or 1.2" and
    "TCG PC Client Specific Implementation Specification for Conventional BIOS"
    """

    EV_PREBOOT_CERT = 0x0
    EV_POST_CODE = 0x1
    EV_UNUSED = 0x2
    EV_NO_ACTION = 0x3
    EV_SEPARATOR = 0x4
    EV_ACTION = 0x5
    EV_EVENT_TAG = 0x6
    EV_S_CRTM_CONTENTS = 0x7
    EV_S_CRTM_VERSION = 0x8
    EV_CPU_MICROCODE = 0x9
    EV_PLATFORM_CONFIG_FLAGS = 0xa
    EV_TABLE_OF_DEVICES = 0xb
    EV_COMPACT_HASH = 0xc
    EV_IPL = 0xd
    EV_IPL_PARTITION_DATA = 0xe
    EV_NONHOST_CODE = 0xf
    EV_NONHOST_CONFIG = 0x10
    EV_NONHOST_INFO = 0x11
    EV_OMIT_BOOT_DEVICE_EVENTS = 0x12

    # TCG EFI Platform Specification For TPM Family 1.1 or 1.2
    EV_EFI_EVENT_BASE = 0x80000000
    EV_EFI_VARIABLE_DRIVER_CONFIG = EV_EFI_EVENT_BASE + 0x1
    EV_EFI_VARIABLE_BOOT = EV_EFI_EVENT_BASE + 0x2
    EV_EFI_BOOT_SERVICES_APPLICATION = EV_EFI_EVENT_BASE + 0x3
    EV_EFI_BOOT_SERVICES_DRIVER = EV_EFI_EVENT_BASE + 0x4
    EV_EFI_RUNTIME_SERVICES_DRIVER = EV_EFI_EVENT_BASE + 0x5
    EV_EFI_GPT_EVENT = EV_EFI_EVENT_BASE + 0x6
    EV_EFI_ACTION = EV_EFI_EVENT_BASE + 0x7
    EV_EFI_PLATFORM_FIRMWARE_BLOB = EV_EFI_EVENT_BASE + 0x8
    EV_EFI_HANDOFF_TABLES = EV_EFI_EVENT_BASE + 0x9
    EV_EFI_VARIABLE_AUTHORITY = EV_EFI_EVENT_BASE + 0xe0

    EVENT_TABLE = {
        EV_PREBOOT_CERT: "EV_PREBOOT_CERT",
        EV_POST_CODE: "EV_POST_CODE",
        EV_UNUSED: "EV_UNUSED",
        EV_NO_ACTION: "EV_NO_ACTION",
        EV_SEPARATOR: "EV_SEPARATOR",
        EV_ACTION: "EV_ACTION",
        EV_EVENT_TAG: "EV_EVENT_TAG",
        EV_S_CRTM_CONTENTS: "EV_S_CRTM_CONTENTS",
        EV_S_CRTM_VERSION: "EV_S_CRTM_VERSION",
        EV_CPU_MICROCODE: "EV_CPU_MICROCODE",
        EV_PLATFORM_CONFIG_FLAGS: "EV_PLATFORM_CONFIG_FLAGS",
        EV_TABLE_OF_DEVICES: "EV_TABLE_OF_DEVICES",
        EV_COMPACT_HASH: "EV_COMPACT_HASH",
        EV_IPL: "EV_IPL",
        EV_IPL_PARTITION_DATA: "EV_IPL_PARTITION_DATA",
        EV_NONHOST_CODE: "EV_NONHOST_CODE",
        EV_NONHOST_CONFIG: "EV_NONHOST_CONFIG",
        EV_NONHOST_INFO: "EV_NONHOST_INFO",
        EV_OMIT_BOOT_DEVICE_EVENTS: "EV_OMIT_BOOT_DEVICE_EVENTS",
        EV_EFI_EVENT_BASE: "EV_EFI_EVENT_BASE",
        EV_EFI_VARIABLE_DRIVER_CONFIG: "EV_EFI_VARIABLE_DRIVER_CONFIG",
        EV_EFI_VARIABLE_BOOT: "EV_EFI_VARIABLE_BOOT",
        EV_EFI_BOOT_SERVICES_APPLICATION: "EV_EFI_BOOT_SERVICES_APPLICATION",
        EV_EFI_BOOT_SERVICES_DRIVER: "EV_EFI_BOOT_SERVICES_DRIVER",
        EV_EFI_RUNTIME_SERVICES_DRIVER: "EV_EFI_RUNTIME_SERVICES_DRIVER",
        EV_EFI_GPT_EVENT: "EV_EFI_GPT_EVENT",
        EV_EFI_ACTION: "EV_EFI_ACTION",
        EV_EFI_PLATFORM_FIRMWARE_BLOB: "EV_EFI_PLATFORM_FIRMWARE_BLOB",
        EV_EFI_HANDOFF_TABLES: "EV_EFI_HANDOFF_TABLES",
        EV_EFI_VARIABLE_AUTHORITY: "EV_EFI_VARIABLE_AUTHORITY"
    }

    @staticmethod
    def get_type_string(event_type):
        """
        Return the type string from given type ID
        """
        if event_type in TDEventLogType.EVENT_TABLE:
            return TDEventLogType.EVENT_TABLE[event_type]
        return "UNKNOWN"


class TCGAlgorithmRegistry:
    """
    From TCG specification
    https://trustedcomputinggroup.org/wp-content/uploads/TCG-_Algorithm_Registry_r1p32_pub.pdf
    """

    TPM_ALG_ERROR = 0x0
    TPM_ALG_RSA = 0x1
    TPM_ALG_TDES = 0x3
    TPM_ALG_SHA256 = 0xB
    TPM_ALG_SHA384 = 0xC
    TPM_ALG_SHA512 = 0xD

    TPM_ALG_TABLE = {
        TPM_ALG_RSA: "TPM_ALG_RSA",
        TPM_ALG_TDES: "TPM_ALG_TDES",
        TPM_ALG_SHA256: "TPM_ALG_SHA256",
        TPM_ALG_SHA384: "TPM_ALG_SHA384",
        TPM_ALG_SHA512: "TPM_ALG_SHA512"
    }

    @staticmethod
    def get_algorithm_string(algoid):
        """
        Return algorithms name from ID
        """
        if algoid in TCGAlgorithmRegistry.TPM_ALG_TABLE:
            return TCGAlgorithmRegistry.TPM_ALG_TABLE[algoid]
        return "UNKNOWN"


class TDEventLogBase:
    """
    Base class for TDX event log entry.
    """

    def __init__(self, address):
        self._address = address
        self._length = 0
        self._data = None
        self._rtmr = 0
        self._etype = 0
        self._digest_count = 0

    @property
    def length(self):
        """
        Length
        """
        return self._length

    @property
    def rtmr(self):
        """
        RTMR register index, RTMR_register_index = RTMR_index - 1
        """
        return self._rtmr

    def parse(self, data):
        """
        Parse abstract function
        """
        raise NotImplementedError

    def parse_header(self, data):
        """
        Parse the header of EventLog
        """
        blob = BinaryBlob(data, self._address)

        index = 0
        td_register_index, index = blob.get_uint32(index)
        self._etype, index = blob.get_uint32(index)
        self._digest_count, index = blob.get_uint32(index)

        self._rtmr = td_register_index - 1
        return (blob, index)

    def dump(self):
        """
        Dump Raw data
        """
        LOG.info("RAW DATA: ----------------------------------------------")
        blob = BinaryBlob(self._data, self._address)
        blob.dump()
        LOG.info("RAW DATA: ----------------------------------------------")


class TDEventLogSpecIdHeader(TDEventLogBase):
    """
    Entry for special ID header
    """

    def __init__(self, address):
        super().__init__(address)
        self._algorithms_number = 0
        self._digest_sizes = {}

    @property
    def digest_sizes(self):
        """
        Property: digest_sizes array
        """
        return self._digest_sizes

    def parse(self, data):
        blob, index = self.parse_header(data)

        index += 20  # 20 zero for digest
        index += 24  # algorithms number
        self._algorithms_number, index = blob.get_uint32(index)

        for _ in range(self._algorithms_number):
            algoid, index = blob.get_uint16(index)
            digestsize, index = blob.get_uint16(index)
            self._digest_sizes[algoid] = digestsize
        vendorsize, index = blob.get_uint8(index)
        index += vendorsize
        self._length = index
        self._data = data[0:index]
        return index

    def dump(self):
        LOG.info("RTMR              : %d", self._rtmr)
        LOG.info("Type              : %d (%s)", self._etype,
                 TDEventLogType.get_type_string(self._etype))
        LOG.info("Length            : %d", self._length)
        LOG.info("Algorithms Number : %d", self._algorithms_number)
        for algoid, size in self._digest_sizes.items():
            LOG.info("  Algorithms[0x%X] Size: %d", algoid, size * 8)
        super().dump()


class TDEventLogEntry(TDEventLogBase):
    """
    Log Entry Class
    """

    def __init__(self, address, specid_header):
        super().__init__(address)
        self._specid_header = specid_header
        self._digests = []
        self._event_size = 0
        self._event = None
        self._algorithms_id = 0

    @property
    def digests(self) -> List:
        """
        Digest is the hash value of raw data in each event log.
        Digests is a list of `digist`.
        """
        return self._digests

    def parse(self, data):
        blob, index = self.parse_header(data)

        for _ in range(self._digest_count):
            algoid, index = blob.get_uint16(index)
            assert algoid in self._specid_header.digest_sizes.keys()
            self._algorithms_id = algoid
            digest_size = self._specid_header.digest_sizes[algoid]
            digest_data, index = blob.get_bytes(index, digest_size)
            self._digests.append(digest_data)
        self._event_size, index = blob.get_uint32(index)
        self._event, index = blob.get_bytes(index, self._event_size)
        self._length = index
        self._data = data[0:index]
        return index

    def dump(self):
        LOG.info("RTMR              : %d", self._rtmr)
        LOG.info("Type              : 0x%X (%s)", self._etype,
                 TDEventLogType.get_type_string(self._etype))
        LOG.info("Length            : %d", self._length)
        LOG.info("Algorithms ID     : %d (%s)", self._algorithms_id,
                 TCGAlgorithmRegistry.get_algorithm_string(self._algorithms_id))
        count = 0
        for digest in self._digests:
            LOG.info("Digest[%d] :", count)
            digest_blob = BinaryBlob(digest)
            digest_blob.dump()
            count += 1
        super().dump()
        LOG.info("")

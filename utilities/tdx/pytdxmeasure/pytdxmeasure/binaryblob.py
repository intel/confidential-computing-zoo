"""
Manage the binary blob
"""
import logging
import string
import struct

LOG = logging.getLogger(__name__)

__author__ = "cpio"


class BinaryBlob:
    """
    Manage the binary blob.
    """

    def __init__(self, data, base=0):
        self._data = data
        self._base_address = base

    @property
    def length(self):
        """
        Length of binary in bytes
        """
        return len(self._data)

    @property
    def data(self):
        """
        Raw data of binary blob
        """
        return self._data

    def to_hex_string(self):
        """
        To hex string
        """
        return "".join(f"{b:02x}" % b for b in self._data)

    def get_uint16(self, pos):
        """
        Get UINT16 integer
        """
        assert pos + 2 <= self.length
        return (struct.unpack("<H", self.data[pos:pos + 2])[0], pos + 2)

    def get_uint8(self, pos):
        """
        Get UINT8 integer
        """
        assert pos + 1 <= self.length
        return (self.data[pos], pos + 1)

    def get_uint32(self, pos):
        """
        Get UINT32 integer
        """
        assert pos + 4 <= self.length
        return (struct.unpack("<L", self.data[pos:pos + 4])[0], pos + 4)

    def get_uint64(self, pos):
        """
        Get UINT64 integer
        """
        assert pos + 8 <= self.length
        return (struct.unpack("<Q", self.data[pos:pos + 8])[0], pos + 8)

    def get_bytes(self, pos, count):
        """
        Get bytes
        """
        if count == 0:
            return None
        assert pos + count <= self.length
        return (self.data[pos:pos + count], pos + count)

    def dump(self):
        """
        Dump Hex value
        """
        index = 0
        linestr = ""
        printstr = ""

        while index < self.length:
            if (index % 16) == 0:
                if len(linestr) != 0:
                    LOG.info("%s %s", linestr, printstr)
                    printstr = ''
                # line prefix string
                # pylint: disable=consider-using-f-string
                linestr = "{0:08X}  ".format(int(index / 16) * 16 + \
                    self._base_address)

            # pylint: disable=consider-using-f-string
            linestr += "{0:02X} ".format(self._data[index])
            if chr(self._data[index]) in set(string.printable) and \
               self._data[index] not in [0xC, 0xB, 0xA, 0xD, 0x9]:
                printstr += chr(self._data[index])
            else:
                printstr += '.'

            index += 1

        if (index % 16) != 0:
            blank = ""
            for _ in range(16 - index % 16):
                blank = blank + "   "
            LOG.info("%s%s %s", linestr, blank, printstr)
        elif index == self.length:
            LOG.info("%s %s", linestr, printstr)

"""
RTMR data structures
"""

from .binaryblob import BinaryBlob


class RTMR(BinaryBlob):
    """
    Data structure for RTMR registers.
    A RTMR register manages a 48-bytes (384-bits) hash value.
    """
    RTMR_COUNT = 4
    RTMR_LENGTH_BY_BYTES = 48

    def __init__(self, data: bytearray = bytearray(RTMR_LENGTH_BY_BYTES),
        base_addr=0):
        super().__init__(data, base_addr)

    def __eq__(self, other):
        bytearray_1, _ = self.get_bytes(0, RTMR.RTMR_LENGTH_BY_BYTES)
        bytearray_2, _ = other.get_bytes(0, RTMR.RTMR_LENGTH_BY_BYTES)

        return bytearray(bytearray_1) == bytearray(bytearray_2)

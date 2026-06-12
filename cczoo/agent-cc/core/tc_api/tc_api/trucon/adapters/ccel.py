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

"""
CCEL (CC Event Log) readers and digest computation.

Reads the CCEL ACPI table header and the sysfs-exported event log bytes used by
TD guests. The trimmed event log is suitable for embedding in Event Log 0.
"""

import base64
import hashlib
import logging
import os
import struct
from typing import Optional

logger = logging.getLogger(__name__)

CCEL_ACPI_PATH = "/sys/firmware/acpi/tables/CCEL"
CCEL_EVENTLOG_PATH = "/sys/firmware/acpi/tables/data/CCEL"


def _read_binary(path: str) -> Optional[bytes]:
    if not os.path.exists(path):
        logger.info("CCEL binary not found at %s", path)
        return None
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception as e:
        logger.warning("Failed to read CCEL from %s: %s", path, e)
        return None


def _read_uint8(buffer: bytes, offset: int) -> tuple[int, int]:
    return buffer[offset], offset + 1


def _read_uint16(buffer: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<H", buffer, offset)[0], offset + 2


def _read_uint32(buffer: bytes, offset: int) -> tuple[int, int]:
    return struct.unpack_from("<I", buffer, offset)[0], offset + 4


def _parse_event_header(buffer: bytes, offset: int) -> tuple[int, int, int, int]:
    register_index, offset = _read_uint32(buffer, offset)
    event_type, offset = _read_uint32(buffer, offset)
    digest_count, offset = _read_uint32(buffer, offset)
    return register_index, event_type, digest_count, offset


def _parse_specid_length(buffer: bytes, start: int) -> tuple[int, dict[int, int]]:
    _, _, _, offset = _parse_event_header(buffer, start)
    offset += 20
    offset += 24
    algorithms_count, offset = _read_uint32(buffer, offset)
    digest_sizes: dict[int, int] = {}
    for _ in range(algorithms_count):
        algorithm_id, offset = _read_uint16(buffer, offset)
        digest_size, offset = _read_uint16(buffer, offset)
        digest_sizes[algorithm_id] = digest_size
    vendor_size, offset = _read_uint8(buffer, offset)
    offset += vendor_size
    return offset - start, digest_sizes


def _parse_event_length(buffer: bytes, start: int, digest_sizes: dict[int, int]) -> int:
    _, _, digest_count, offset = _parse_event_header(buffer, start)
    for _ in range(digest_count):
        algorithm_id, offset = _read_uint16(buffer, offset)
        offset += digest_sizes[algorithm_id]
    event_size, offset = _read_uint32(buffer, offset)
    offset += event_size
    return offset - start


def trim_ccel_eventlog_binary(data: bytes) -> bytes:
    """Trim the sysfs-exported CCEL log to the bytes consumed before the sentinel."""
    if not data:
        return data

    try:
        offset = 0
        specid_length, digest_sizes = _parse_specid_length(data, offset)
        offset += specid_length

        while offset + 8 <= len(data):
            register_index = struct.unpack_from("<I", data, offset)[0]
            if register_index == 0xFFFFFFFF:
                break
            offset += _parse_event_length(data, offset, digest_sizes)
        return data[:offset]
    except Exception as exc:
        logger.warning("Failed to trim CCEL event log cleanly, keeping raw sysfs payload: %s", exc)
        return data


def read_ccel_binary(path: str = CCEL_ACPI_PATH) -> Optional[bytes]:
    """Read the raw CCEL binary from the ACPI tables path.

    Returns None if the file does not exist (non-TEE or no CCEL support).
    """
    return _read_binary(path)


def read_ccel_eventlog_binary(path: str = CCEL_EVENTLOG_PATH) -> Optional[bytes]:
    """Read the sysfs-exported CCEL event log region."""
    return _read_binary(path)


def read_ccel_eventlog_used_binary(path: str = CCEL_EVENTLOG_PATH) -> Optional[bytes]:
    """Read and trim the CCEL event log to the bytes consumed by actual entries."""
    data = read_ccel_eventlog_binary(path)
    if data is None:
        return None
    return trim_ccel_eventlog_binary(data)


def read_ccel_eventlog_b64(path: str = CCEL_EVENTLOG_PATH) -> Optional[str]:
    """Read the used CCEL event log bytes and return them base64-encoded."""
    data = read_ccel_eventlog_used_binary(path)
    if data is None:
        return None
    return base64.b64encode(data).decode("ascii")


def compute_ccel_digest(path: str = CCEL_ACPI_PATH) -> Optional[str]:
    """Compute SHA-384 digest of the raw CCEL binary.

    Returns 'sha384:<hex>' or None if CCEL is not available.
    """
    data = read_ccel_binary(path)
    if data is None:
        return None
    return "sha384:" + hashlib.sha384(data).hexdigest()

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

"""Tests for CCEL reading, trimming, and digest computation."""

import base64
import hashlib
import os
import struct

from tc_api.trucon.adapters.ccel import (
    compute_ccel_digest,
    read_ccel_binary,
    read_ccel_eventlog_b64,
    read_ccel_eventlog_used_binary,
    trim_ccel_eventlog_binary,
)


class TestReadCcelBinary:
    def test_reads_existing_file(self, tmp_path):
        ccel_file = tmp_path / "CCEL"
        data = b"\x01\x02\x03" * 100
        ccel_file.write_bytes(data)

        result = read_ccel_binary(str(ccel_file))
        assert result == data

    def test_returns_none_when_missing(self, tmp_path):
        result = read_ccel_binary(str(tmp_path / "nonexistent"))
        assert result is None

    def test_returns_none_on_read_error(self, tmp_path):
        # Create a directory where a file is expected — causes read error
        fake = tmp_path / "CCEL"
        fake.mkdir()

        result = read_ccel_binary(str(fake))
        assert result is None


class TestComputeCcelDigest:
    def test_digest_of_available_ccel(self, tmp_path):
        ccel_file = tmp_path / "CCEL"
        data = b"\xaa\xbb\xcc" * 50
        ccel_file.write_bytes(data)

        result = compute_ccel_digest(str(ccel_file))
        expected = "sha384:" + hashlib.sha384(data).hexdigest()
        assert result == expected

    def test_digest_when_absent(self, tmp_path):
        result = compute_ccel_digest(str(tmp_path / "nonexistent"))
        assert result is None

    def test_digest_deterministic(self, tmp_path):
        ccel_file = tmp_path / "CCEL"
        data = os.urandom(4096)
        ccel_file.write_bytes(data)

        d1 = compute_ccel_digest(str(ccel_file))
        d2 = compute_ccel_digest(str(ccel_file))
        assert d1 == d2
        assert d1.startswith("sha384:")
        assert len(d1) == len("sha384:") + 96  # 384 bits = 96 hex chars


class TestReadTrimmedEventLog:
    @staticmethod
    def _sample_eventlog() -> bytes:
        specid = (
            struct.pack("<III", 1, 3, 0)
            + (b"\x00" * 16)
            + struct.pack("<I", 33)
            + b"Spec ID Event03\x00"
            + struct.pack("<I", 0)
            + struct.pack("<BBBB", 0, 2, 0, 2)
            + struct.pack("<I", 1)
            + struct.pack("<HH", 0x0C, 48)
            + struct.pack("<B", 0)
        )
        event_data = b"test"
        event = (
            struct.pack("<III", 2, 0x0D, 1)
            + struct.pack("<H", 0x0C)
            + (b"\x11" * 48)
            + struct.pack("<I", len(event_data))
            + event_data
        )
        sentinel = bytes.fromhex("ffffffff00000000")
        return specid + event + sentinel + (b"\x00" * 32)

    def test_trims_to_used_bytes_before_sentinel(self):
        data = self._sample_eventlog()
        trimmed = trim_ccel_eventlog_binary(data)
        assert len(trimmed) == len(data) - 8 - 32
        assert trimmed.endswith(b"test")

    def test_reads_trimmed_eventlog_from_file(self, tmp_path):
        eventlog_file = tmp_path / "CCEL"
        data = self._sample_eventlog()
        eventlog_file.write_bytes(data)

        trimmed = read_ccel_eventlog_used_binary(str(eventlog_file))
        assert trimmed == trim_ccel_eventlog_binary(data)

    def test_reads_trimmed_eventlog_as_base64(self, tmp_path):
        eventlog_file = tmp_path / "CCEL"
        data = self._sample_eventlog()
        eventlog_file.write_bytes(data)

        result = read_ccel_eventlog_b64(str(eventlog_file))
        assert result == base64.b64encode(trim_ccel_eventlog_binary(data)).decode("ascii")

"""Tests for CCEL reading and digest computation."""

import hashlib
import os
import pytest

from tc_api.trucon.adapters.ccel import read_ccel_binary, compute_ccel_digest


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

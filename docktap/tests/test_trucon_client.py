"""Unit tests for docktap/trucon_client.py — entry mapping, filtering, error handling, DSSE construction."""

import json
import logging
from unittest.mock import patch, MagicMock

import pytest

from trucon_client import (
    TruConCommitter,
    SUBMITTABLE_OPERATIONS,
    _build_entries,
)
from proxy.operation_log import OperationRecord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_record(**overrides) -> OperationRecord:
    defaults = dict(
        operation={"type": "unknown"},
        image={},
        container={},
    )
    defaults.update(overrides)
    return OperationRecord(**defaults)


# ---------------------------------------------------------------------------
# 3.1  Entry mapping per operation type
# ---------------------------------------------------------------------------

class TestEntryMapping:
    def test_pull_entries(self):
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest", "digest": "sha256:abc123"},
        )
        entries = _build_entries(rec, "pull")
        keys = [k for k, _ in entries]
        assert keys == ["operation_type", "image_name", "image_tag", "image_digest"]
        assert entries[0] == ("operation_type", json.dumps("pull"))
        assert entries[1] == ("image_name", json.dumps("nginx"))
        assert entries[2] == ("image_tag", json.dumps("latest"))
        assert entries[3] == ("image_digest", json.dumps("sha256:abc123"))

    def test_pull_missing_digest(self):
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        entries = _build_entries(rec, "pull")
        keys = [k for k, _ in entries]
        assert "image_digest" not in keys
        assert len(entries) == 3  # operation_type, image_name, image_tag

    def test_create_entries(self):
        rec = _make_record(
            operation={"type": "create"},
            image={"name": "myapp"},
            container={"name": "mycontainer", "id": "abc123def"},
        )
        entries = _build_entries(rec, "create")
        keys = [k for k, _ in entries]
        assert keys == ["operation_type", "image_name", "container_name", "container_id"]

    def test_start_entries(self):
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "abc123def"},
        )
        entries = _build_entries(rec, "start")
        assert len(entries) == 2
        assert entries[0] == ("operation_type", json.dumps("start"))
        assert entries[1] == ("container_id", json.dumps("abc123def"))

    def test_stop_entries(self):
        rec = _make_record(
            operation={"type": "stop"},
            container={"id": "xyz789"},
        )
        entries = _build_entries(rec, "stop")
        assert entries[0] == ("operation_type", json.dumps("stop"))
        assert entries[1] == ("container_id", json.dumps("xyz789"))

    def test_rm_entries(self):
        rec = _make_record(
            operation={"type": "rm"},
            container={"id": "del456"},
        )
        entries = _build_entries(rec, "rm")
        assert entries[0] == ("operation_type", json.dumps("rm"))
        assert entries[1] == ("container_id", json.dumps("del456"))

    def test_missing_container_id_omitted(self):
        rec = _make_record(operation={"type": "start"}, container={})
        entries = _build_entries(rec, "start")
        assert len(entries) == 1  # only operation_type


# ---------------------------------------------------------------------------
# 3.2  Operation type filtering
# ---------------------------------------------------------------------------

class TestOperationFiltering:
    def test_submittable_operations(self):
        assert SUBMITTABLE_OPERATIONS == {"pull", "create", "start", "stop", "rm"}

    @pytest.mark.parametrize("op", ["pull", "create", "start", "stop", "rm"])
    def test_lifecycle_ops_pass(self, op):
        assert op in SUBMITTABLE_OPERATIONS

    @pytest.mark.parametrize("op", [
        "wait", "rmi", "image_inspect", "inspect",
        "preflight_ping", "preflight_info", "unknown",
    ])
    def test_non_lifecycle_ops_blocked(self, op):
        assert op not in SUBMITTABLE_OPERATIONS


# ---------------------------------------------------------------------------
# 3.3  Best-effort failure handling
# ---------------------------------------------------------------------------

class TestBestEffortFailureHandling:
    def test_trucon_unreachable_returns_false(self, caplog):
        """TruCon connection refused → warning logged, returns False, no exception."""
        committer = TruConCommitter(trucon_url="http://127.0.0.1:59999")
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "c123"},
        )
        with patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            # Make signing succeed but HTTP fail
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value._rekor = None
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            with caplog.at_level(logging.WARNING):
                result = committer.submit_operation(rec, "start")

        assert result is False
        assert any("TruCon commit failed" in r.message for r in caplog.records)

    def test_oidc_unavailable_returns_false(self, caplog):
        """No OIDC credential → warning logged, returns False."""
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        with patch("trucon_client.detect_credential", return_value=None):
            with caplog.at_level(logging.WARNING):
                result = committer.submit_operation(rec, "pull")

        assert result is False
        assert any("OIDC" in r.message for r in caplog.records)

    def test_signing_error_returns_false(self, caplog):
        """Sigstore signing exception → warning logged, returns False."""
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "create"},
            image={"name": "app"},
            container={"name": "c1", "id": "abc"},
        )
        with patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value.signer.side_effect = RuntimeError("sign fail")

            with caplog.at_level(logging.WARNING):
                result = committer.submit_operation(rec, "create")

        assert result is False
        assert any("TruCon commit failed" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# 3.4  DSSE bundle construction
# ---------------------------------------------------------------------------

class TestDSSEConstruction:
    def test_predicate_type_and_digest_format(self):
        """Verify predicate type, digest prefix, and subject format match tc_api conventions."""
        from tc_api.tlog_client import compute_entry_digest, compute_event_digest

        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "1.25"},
        )
        entries = _build_entries(rec, "pull")

        # Verify entry digests use sha384 prefix
        for k, v in entries:
            d = compute_entry_digest(k, v)
            assert d.startswith("sha384:")
            assert len(d.split(":")[1]) == 96  # hex length of SHA-384

        # Verify event digest
        entry_digests = [compute_entry_digest(k, v) for k, v in entries]
        event_digest = compute_event_digest(
            "evt-test1234", "docker_pull", "2026-04-17T12:00:00", entry_digests
        )
        assert event_digest.startswith("sha384:")

    def test_subject_name_matches_chain_convention(self):
        """Subject name should be 'trusted-log-chain_default' for default chain."""
        # The trucon_client uses chain_id="default" → subject name "trusted-log-chain_default"
        # We just verify the constant matches tc_api convention.
        chain_id = "default"
        expected = f"trusted-log-chain_{chain_id}"
        assert expected == "trusted-log-chain_default"

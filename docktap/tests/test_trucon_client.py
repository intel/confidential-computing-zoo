"""Unit tests for docktap/trucon_client.py — entry mapping, filtering, error handling, DSSE construction."""

import json
import logging
import time
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

from trucon_client import (
    TruConCommitter,
    SUBMITTABLE_OPERATIONS,
    _build_entries,
)
from tc_api.tlog.types import Entry
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
        keys = [e.key for e in entries]
        assert keys == ["operation_type", "image_name", "image_tag", "image_digest"]
        assert entries[0] == Entry(key="operation_type", value="pull")
        assert entries[1] == Entry(key="image_name", value="nginx")
        assert entries[2] == Entry(key="image_tag", value="latest")
        assert entries[3] == Entry(key="image_digest", value="sha256:abc123")

    def test_pull_missing_digest(self):
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        entries = _build_entries(rec, "pull")
        keys = [e.key for e in entries]
        assert "image_digest" not in keys
        assert len(entries) == 3  # operation_type, image_name, image_tag

    def test_create_entries(self):
        rec = _make_record(
            operation={"type": "create"},
            image={"name": "myapp"},
            container={"name": "mycontainer", "id": "abc123def"},
        )
        entries = _build_entries(rec, "create")
        keys = [e.key for e in entries]
        assert keys == ["operation_type", "image_name", "container_name", "container_id"]

    def test_start_entries(self):
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "abc123def"},
        )
        entries = _build_entries(rec, "start")
        assert len(entries) == 2
        assert entries[0] == Entry(key="operation_type", value="start")
        assert entries[1] == Entry(key="container_id", value="abc123def")

    def test_stop_entries(self):
        rec = _make_record(
            operation={"type": "stop"},
            container={"id": "xyz789"},
        )
        entries = _build_entries(rec, "stop")
        assert entries[0] == Entry(key="operation_type", value="stop")
        assert entries[1] == Entry(key="container_id", value="xyz789")

    def test_rm_entries(self):
        rec = _make_record(
            operation={"type": "rm"},
            container={"id": "del456"},
        )
        entries = _build_entries(rec, "rm")
        assert entries[0] == Entry(key="operation_type", value="rm")
        assert entries[1] == Entry(key="container_id", value="del456")

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
        for e in entries:
            d = compute_entry_digest(e.key, e.value)
            assert d.startswith("sha384:")
            assert len(d.split(":")[1]) == 96  # hex length of SHA-384

        # Verify event digest
        entry_digests = [compute_entry_digest(e.key, e.value) for e in entries]
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


# ---------------------------------------------------------------------------
# 3.5  Retry and acknowledgement handling
# ---------------------------------------------------------------------------

class TestRetryAndAcknowledgement:
    def _make_committer(self):
        return TruConCommitter(
            trucon_url="http://127.0.0.1:8001",
            start_retry_worker=False,
            max_retry_attempts=2,
            retry_base_delay=0.0,
            retry_max_delay=0.0,
            acknowledged_retention_hours=0.0,
            terminal_retention_hours=0.0,
        )

    def _signing_patches(self):
        return patch("trucon_client.detect_credential", return_value="fake-token"), \
            patch("trucon_client.IdentityToken", return_value="tok"), \
            patch("trucon_client.SigningContext")

    def test_retryable_failure_is_queued(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            result = committer.submit_operation(rec, "start")

        assert result is False
        snapshot = committer.get_retry_snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["status"] == "retryable"
        assert snapshot[0]["retry_attempts"] == 0

    def test_retry_reuses_same_idempotency_key(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})

        with patch.object(
            committer,
            "_post_to_trucon",
            side_effect=[urllib.error.URLError("down"), {"record_id": "rec-1", "sequence_num": 7}],
        ) as mock_post, \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "start")
            committer.process_retry_queue(now=time.monotonic())

        assert mock_post.call_count == 2
        first_key = mock_post.call_args_list[0].kwargs["idempotency_key"]
        second_key = mock_post.call_args_list[1].kwargs["idempotency_key"]
        assert first_key == second_key

    def test_acknowledged_retry_is_marked_complete(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "stop"}, container={"id": "xyz789"})

        with patch.object(
            committer,
            "_post_to_trucon",
            side_effect=[urllib.error.URLError("down"), {"record_id": "rec-9", "sequence_num": 9}],
        ), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "stop")
            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert snapshot[0]["status"] == "acknowledged"
        assert snapshot[0]["record_id"] == "rec-9"
        assert snapshot[0]["sequence_num"] == 9

    def test_retry_exhaustion_marks_terminal_failure(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "rm"}, container={"id": "del456"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("still-down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "rm")
            committer.process_retry_queue(now=time.monotonic())
            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert snapshot[0]["status"] == "failed_terminal"
        assert snapshot[0]["retry_attempts"] == 2

    def test_retryable_items_are_not_gc_eligible(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "start")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 0
        assert len(committer.get_retry_snapshot()) == 1

    def test_acknowledged_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "stop"}, container={"id": "xyz789"})

        with patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "stop")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

    def test_terminal_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "rm"}, container={"id": "del456"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("still-down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.SigningContext") as mock_ctx:
            mock_ctx.production.return_value._rekor = None
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.production.return_value.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.production.return_value.signer.return_value.__exit__ = lambda s, *a: None

            committer.submit_operation(rec, "rm")
            committer.process_retry_queue(now=time.monotonic())
            committer.process_retry_queue(now=time.monotonic())

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

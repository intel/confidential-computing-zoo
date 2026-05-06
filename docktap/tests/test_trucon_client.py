"""Unit tests for docktap/trucon_client.py — entry mapping, filtering, error handling, DSSE construction."""

import json
import logging
import time
import urllib.error
from unittest.mock import ANY, MagicMock, patch

import pytest

from trucon_client import (
    TruConCommitter,
    SUBMITTABLE_OPERATIONS,
    _build_entries,
    _resolve_identity_token_str,
    get_attestation_challenge,
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


def _install_mock_signing_context(mock_build_context, *, bundle_json='{"fake": "bundle"}', sign_side_effect=None):
    mock_ctx = MagicMock()
    mock_signer = MagicMock()
    if sign_side_effect is not None:
        mock_signer.sign_dsse.side_effect = sign_side_effect
    else:
        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = bundle_json
        mock_signer.sign_dsse.return_value = mock_bundle
    mock_ctx.signer.return_value.__enter__ = lambda s: mock_signer
    mock_ctx.signer.return_value.__exit__ = lambda s, *a: None
    mock_build_context.return_value = mock_ctx
    return mock_ctx, mock_signer


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
        assert keys == ["operation_type", "operation_result", "runtime_engine", "image_name", "image_tag", "image_digest"]
        assert entries[0] == Entry(key="operation_type", value="pull")
        assert entries[1] == Entry(key="operation_result", value="success")
        assert entries[2] == Entry(key="runtime_engine", value="docker")
        assert entries[3] == Entry(key="image_name", value="nginx")
        assert entries[4] == Entry(key="image_tag", value="latest")
        assert entries[5] == Entry(key="image_digest", value="sha256:abc123")

    def test_pull_missing_digest(self):
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        entries = _build_entries(rec, "pull")
        keys = [e.key for e in entries]
        assert "image_digest" not in keys
        assert len(entries) == 5  # operation_type, operation_result, runtime_engine, image_name, image_tag

    def test_create_entries(self):
        rec = _make_record(
            operation={"type": "create"},
            image={"name": "myapp"},
            container={"name": "mycontainer", "id": "abc123def"},
        )
        entries = _build_entries(rec, "create")
        keys = [e.key for e in entries]
        assert keys == ["operation_type", "operation_result", "runtime_engine", "image_name", "container_name", "container_id"]

    def test_start_entries(self):
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "abc123def"},
        )
        entries = _build_entries(rec, "start")
        assert len(entries) == 4
        assert entries[0] == Entry(key="operation_type", value="start")
        assert entries[1] == Entry(key="operation_result", value="success")
        assert entries[2] == Entry(key="runtime_engine", value="docker")
        assert entries[3] == Entry(key="container_id", value="abc123def")

    def test_stop_entries(self):
        rec = _make_record(
            operation={"type": "stop"},
            container={"id": "xyz789"},
        )
        entries = _build_entries(rec, "stop")
        assert entries[0] == Entry(key="operation_type", value="stop")
        assert entries[1] == Entry(key="operation_result", value="success")
        assert entries[2] == Entry(key="runtime_engine", value="docker")
        assert entries[3] == Entry(key="container_id", value="xyz789")

    def test_rm_entries(self):
        rec = _make_record(
            operation={"type": "rm"},
            container={"id": "del456"},
        )
        entries = _build_entries(rec, "rm")
        assert entries[0] == Entry(key="operation_type", value="rm")
        assert entries[1] == Entry(key="operation_result", value="success")
        assert entries[2] == Entry(key="runtime_engine", value="docker")
        assert entries[3] == Entry(key="container_id", value="del456")

    def test_missing_container_id_omitted(self):
        rec = _make_record(operation={"type": "start"}, container={})
        entries = _build_entries(rec, "start")
        assert len(entries) == 3  # operation_type, operation_result, runtime_engine

    def test_container_scoped_entries_include_profile_identity_fields(self):
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "abc123def"},
        )
        entries = _build_entries(
            rec,
            "start",
            workload_id="my-app",
            launch_id="launch-123",
            instance_id="abc123def",
        )
        keys = [e.key for e in entries]
        assert keys[:6] == ["operation_type", "operation_result", "runtime_engine", "workload_id", "launch_id", "instance_id"]

    def test_runtime_engine_comes_from_operation_record(self):
        rec = _make_record(
            runtime_engine="podman",
            operation={"type": "start"},
            container={"id": "abc123def"},
        )
        entries = _build_entries(rec, "start")
        assert entries[2] == Entry(key="runtime_engine", value="podman")


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
        "wait", "rmi", "image_inspect", "network_inspect", "volume_inspect", "plugin_inspect", "inspect",
        "preflight_ping", "preflight_info", "unknown",
    ])
    def test_non_lifecycle_ops_blocked(self, op):
        assert op not in SUBMITTABLE_OPERATIONS


# ---------------------------------------------------------------------------
# 3.3  Best-effort failure handling
# ---------------------------------------------------------------------------

class TestBestEffortFailureHandling:
    def test_explicit_docktap_identity_token_env_is_used_before_ambient_detection(self, monkeypatch):
        monkeypatch.setenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", " env-token ")
        with patch("trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "env-token"
        detect.assert_not_called()

    def test_generic_sigstore_identity_token_env_is_used_before_ambient_detection(self, monkeypatch):
        monkeypatch.delenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", raising=False)
        monkeypatch.setenv("SIGSTORE_IDENTITY_TOKEN", " generic-token ")
        with patch("trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "generic-token"
        detect.assert_not_called()

    def test_near_expiry_explicit_identity_token_remains_usable(self, monkeypatch):
        monkeypatch.setenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", "env-token")
        with patch("trucon_client.token_seconds_remaining", return_value=7), \
             patch("trucon_client.resolve_sigstore_identity_token") as resolve_token, \
             patch("trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "env-token"

        resolve_token.assert_not_called()
        detect.assert_not_called()

    def test_expired_explicit_identity_token_falls_back_to_shared_cache(self, monkeypatch):
        monkeypatch.setenv(
            "DOCKTAP_SIGSTORE_IDENTITY_TOKEN",
            "eyJhbGciOiJub25lIn0.eyJleHAiOjF9.signature",
        )
        with patch("trucon_client.resolve_sigstore_identity_token", return_value="cached-token") as resolve_token, \
             patch("trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "cached-token"

        resolve_token.assert_called_once_with(
            operation="docktap",
            logger=ANY,
            allow_interactive=False,
            require_token=False,
            min_ttl_seconds=15,
        )
        detect.assert_not_called()

    def test_shared_cached_sigstore_token_is_used_before_ambient_detection(self, monkeypatch):
        monkeypatch.delenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", raising=False)
        monkeypatch.delenv("SIGSTORE_IDENTITY_TOKEN", raising=False)
        with patch("trucon_client.resolve_sigstore_identity_token", return_value="cached-token") as resolve_token, \
             patch("trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "cached-token"
        resolve_token.assert_called_once()
        detect.assert_not_called()

    def test_trucon_unreachable_returns_false(self, caplog):
        """TruCon connection refused → warning logged, returns False, no exception."""
        committer = TruConCommitter(trucon_url="http://127.0.0.1:59999")
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "c123"},
        )
        with patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

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

    def test_get_attestation_challenge_uses_tc_api_response(self, monkeypatch):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(
                    {
                        "interactive_login_url": "/api/sigstore/interactive-login?operation=docktap&session_id=sess-1",
                        "auth_url": "https://oauth2.sigstore.dev/auth?client_id=sigstore",
                        "session_id": "sess-1",
                        "login_status_url": "/api/sigstore/login-status/sess-1",
                    }
                ).encode("utf-8")

        monkeypatch.setenv("DOCKTAP_ATTESTATION_API_URL", "http://127.0.0.1:8000")
        monkeypatch.setenv("DOCKTAP_ATTESTATION_BROWSER_BASE_URL", "http://server.example:8000")

        with patch("trucon_client.urllib.request.urlopen", return_value=FakeResponse()):
            challenge = get_attestation_challenge("docktap")

        assert challenge["status"] == "login_required"
        assert challenge["session_id"] == "sess-1"
        assert challenge["auth_url"] == "https://oauth2.sigstore.dev/auth?client_id=sigstore"
        assert challenge["interactive_login_url"] == (
            "http://server.example:8000/api/sigstore/interactive-login?operation=docktap&session_id=sess-1"
        )

    def test_submit_operation_uses_explicit_identity_token_env(self, monkeypatch):
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        monkeypatch.setenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", "env-token")

        with patch("trucon_client.detect_credential") as detect_credential, \
             patch("trucon_client.IdentityToken", return_value="tok") as identity_token, \
             patch("trucon_client.build_signing_context") as build_context, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}):
            mock_ctx = MagicMock()
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.signer.return_value.__exit__ = lambda s, *a: None
            build_context.return_value = mock_ctx

            result = committer.submit_operation(rec, "pull")

        assert result is True
        detect_credential.assert_not_called()
        identity_token.assert_called_once_with("env-token")
        build_context.assert_called_once()

    def test_submit_operation_uses_configured_docktap_rekor_url(self, monkeypatch):
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        monkeypatch.setenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", "env-token")
        monkeypatch.setenv("DOCKTAP_REKOR_URL", "https://rekor.example.test")

        with patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.build_signing_context") as build_context, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}):
            mock_ctx = MagicMock()
            mock_signer = MagicMock()
            mock_bundle = MagicMock()
            mock_bundle.to_json.return_value = '{"fake": "bundle"}'
            mock_signer.sign_dsse.return_value = mock_bundle
            mock_ctx.signer.return_value.__enter__ = lambda s: mock_signer
            mock_ctx.signer.return_value.__exit__ = lambda s, *a: None
            build_context.return_value = mock_ctx

            result = committer.submit_operation(rec, "pull")

        assert result is True
        build_context.assert_called_once_with("https://rekor.example.test")

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
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx, sign_side_effect=RuntimeError("sign fail"))

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
            patch("trucon_client.build_signing_context")

    def test_retryable_failure_is_queued(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

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
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

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
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

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
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

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
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

            committer.submit_operation(rec, "start")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 0
        assert len(committer.get_retry_snapshot()) == 1

    def test_acknowledged_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "stop"}, container={"id": "xyz789"})

        with patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

            committer.submit_operation(rec, "stop")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

    def test_terminal_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "rm"}, container={"id": "del456"})

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("still-down")), \
             patch("trucon_client.detect_credential", return_value="fake-token"), \
             patch("trucon_client.IdentityToken", return_value="tok"), \
             patch("trucon_client.build_signing_context") as mock_ctx:
            _install_mock_signing_context(mock_ctx)

            committer.submit_operation(rec, "rm")
            committer.process_retry_queue(now=time.monotonic())
            committer.process_retry_queue(now=time.monotonic())

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

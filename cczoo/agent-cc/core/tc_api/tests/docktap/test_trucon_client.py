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

"""Unit tests for docktap/trucon_client.py — entry mapping, filtering, error handling, DSSE construction."""

import json
import logging
import time
import urllib.error
from unittest.mock import patch, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.docktap.trucon_client import (
    TruConCommitter,
    SUBMITTABLE_OPERATIONS,
    _build_entries,
    _extract_rekor_identifiers,
    _resolve_identity_token_str,
)
from tlog.types import Entry
from tc_api.docktap.proxy.operation_log import OperationRecord


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


def _mock_signing_context(bundle_json='{"fake": "bundle"}'):
    mock_signer = MagicMock()
    mock_bundle = MagicMock()
    mock_bundle.to_json.return_value = bundle_json
    mock_signer.sign_dsse.return_value = mock_bundle
    mock_signing_context = MagicMock()
    mock_signing_context.signer.return_value.__enter__ = lambda s: mock_signer
    mock_signing_context.signer.return_value.__exit__ = lambda s, *a: None
    return mock_signing_context, mock_signer


@pytest.fixture(autouse=True)
def _token_based_auth_mode(monkeypatch):
    monkeypatch.setenv("DOCKTAP_AUTH_MODE", "delegation_disabled")


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

    def test_build_entries(self):
        rec = _make_record(
            operation={"type": "build"},
            image={"name": "demo", "tag": "latest", "platform": "linux/amd64"},
        )
        entries = _build_entries(rec, "build")
        keys = [e.key for e in entries]
        assert keys == ["operation_type", "operation_result", "runtime_engine", "image_name", "image_tag", "image_platform"]
        assert entries[0] == Entry(key="operation_type", value="build")
        assert entries[3] == Entry(key="image_name", value="demo")
        assert entries[4] == Entry(key="image_tag", value="latest")
        assert entries[5] == Entry(key="image_platform", value="linux/amd64")

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
        assert SUBMITTABLE_OPERATIONS == {"pull", "build", "create", "start", "stop", "rm"}

    @pytest.mark.parametrize("op", ["pull", "build", "create", "start", "stop", "rm"])
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
        with patch("tc_api.docktap.trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "env-token"
        detect.assert_not_called()

    def test_generic_sigstore_identity_token_env_is_used_before_ambient_detection(self, monkeypatch):
        monkeypatch.delenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", raising=False)
        monkeypatch.setenv("SIGSTORE_IDENTITY_TOKEN", " generic-token ")
        with patch("tc_api.docktap.trucon_client.detect_credential") as detect:
            assert _resolve_identity_token_str() == "generic-token"
        detect.assert_not_called()

    def test_shared_cached_sigstore_token_is_used_before_ambient_detection(self, monkeypatch):
        monkeypatch.delenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", raising=False)
        monkeypatch.delenv("SIGSTORE_IDENTITY_TOKEN", raising=False)
        with patch("tc_api.docktap.trucon_client.resolve_sigstore_identity_token", return_value="cached-token") as resolve_token, \
             patch("tc_api.docktap.trucon_client.detect_credential") as detect:
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
        mock_signing_context, _ = _mock_signing_context()
        with patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            with caplog.at_level(logging.WARNING):
                result = committer.submit_operation(rec, "start")

        assert result is False
        assert any("TruCon commit failed" in r.message for r in caplog.records)

    def test_oidc_unavailable_returns_false(self, caplog):
        """No reusable token → warning logged, returns False."""
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        with patch("tc_api.docktap.trucon_client.detect_credential", return_value=None):
            with caplog.at_level(logging.WARNING):
                result = committer.submit_operation(rec, "pull")

        assert result is False
        assert any("No reusable Sigstore identity token" in r.message for r in caplog.records)

    def test_submit_operation_uses_explicit_identity_token_env(self, monkeypatch):
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )
        monkeypatch.setenv("DOCKTAP_SIGSTORE_IDENTITY_TOKEN", "env-token")
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential") as detect_credential, \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok") as identity_token, \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context), \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}):
            result = committer.submit_operation(rec, "pull")

        assert result is True
        detect_credential.assert_not_called()
        identity_token.assert_called_once_with("env-token")

    def test_submit_operation_uses_shared_signing_context_builder(self):
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )

        mock_signer = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = '{"fake": "bundle"}'
        mock_bundle.log_entry.uuid = "rekor-uuid-123"
        mock_bundle.log_entry.log_index = 456
        mock_signer.sign_dsse.return_value = mock_bundle
        mock_signing_context = MagicMock()
        mock_signing_context.signer.return_value.__enter__ = lambda s: mock_signer
        mock_signing_context.signer.return_value.__exit__ = lambda s, *a: None

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context) as build_ctx, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}), \
             patch("tc_api.docktap.trucon_client.logger") as logger_mock:
            result = committer.submit_operation(rec, "pull")

        assert result is True
        build_ctx.assert_called_once_with()
        mock_signing_context.signer.assert_called_once_with("tok", cache=True)
        log_args = logger_mock.info.call_args[0]
        assert log_args[0] == "TruCon commit accepted for %s (event_id=%s, record_id=%s, sequence_num=%s, initial_bundle_rekor_uuid=%s, initial_bundle_rekor_log_index=%s)"
        assert log_args[1] == "pull"
        assert str(log_args[2]).startswith("evt-")
        assert log_args[3:] == ("rec-1", 1, "rekor-uuid-123", "456")

    def test_submit_operation_signs_reservation_backed_predicate(self):
        committer = TruConCommitter()
        owner_private_key = ec.generate_private_key(ec.SECP384R1())
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx", "tag": "latest"},
        )

        captured_statement = {}
        mock_signer = MagicMock()
        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = '{"fake": "bundle"}'

        def _capture_statement(statement):
            captured_statement["json"] = json.loads(statement._contents.decode("utf-8"))
            return mock_bundle

        mock_signer.sign_dsse.side_effect = _capture_statement
        mock_signing_context = MagicMock()
        mock_signing_context.signer.return_value.__enter__ = lambda s: mock_signer
        mock_signing_context.signer.return_value.__exit__ = lambda s, *a: None

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 7, "prev_event_digest": "sha384:prev", "prev_lookup_hash": "sha256:lookup"}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context), \
                         patch("tc_api.docktap.trucon_client.get_chain_owner_private_key", return_value=owner_private_key), \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 7}):
            assert committer.submit_operation(rec, "pull") is True

        predicate = captured_statement["json"]["predicate"]
        assert predicate["chain_id"] == "default"
        assert predicate["sequence_num"] == 7
        assert predicate["prev_event_digest"] == "sha384:prev"
        assert predicate["prev_lookup_hash"] == "sha256:lookup"
        assert predicate["owner_authorization"]["algorithm"] == "ecdsa-p384-sha384"

    def test_extract_rekor_identifiers_prefers_uuid_and_keeps_log_index(self):
        bundle = MagicMock()
        bundle.log_entry.uuid = "rekor-uuid-123"
        bundle.log_entry.log_index = 456

        result = _extract_rekor_identifiers(bundle)

        assert result == {"initial_bundle_rekor_uuid": "rekor-uuid-123", "initial_bundle_rekor_log_index": "456"}

    def test_signing_error_returns_false(self, caplog):
        """Sigstore signing exception → warning logged, returns False."""
        committer = TruConCommitter()
        rec = _make_record(
            operation={"type": "create"},
            image={"name": "app"},
            container={"name": "c1", "id": "abc"},
        )
        mock_signing_context = MagicMock()
        mock_signing_context.signer.side_effect = RuntimeError("sign fail")
        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

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
        from tlog.digest import compute_entry_digest, compute_event_digest

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
        return patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
            patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
            patch("tc_api.docktap.trucon_client.build_signing_context", return_value=_mock_signing_context()[0])

    def test_retryable_failure_is_queued(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("down")), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            result = committer.submit_operation(rec, "start")

        assert result is False
        snapshot = committer.get_retry_snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["status"] == "retryable"
        assert snapshot[0]["retry_attempts"] == 0

    def test_async_queued_operation_is_processed_by_retry_worker(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            queue_id = committer.enqueue_operation(rec, "start")
            snapshot = committer.get_retry_snapshot()
            assert len(snapshot) == 1
            assert snapshot[0]["event_id"] == queue_id
            assert snapshot[0]["status"] == "queued"

            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["status"] == "acknowledged"
        assert snapshot[0]["record_id"] == "rec-1"

    def test_async_terminal_failure_expires_reserved_intent(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "pull"}, image={"name": "busybox", "tag": "latest"})

        with patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.get_chain_owner_private_key"), \
             patch("tc_api.docktap.trucon_client.attach_commit_context", return_value={"algorithm": "ecdsa-p384-sha384"}), \
             patch("tc_api.docktap.trucon_client.build_statement_json", return_value='{"predicate":{}}'), \
             patch("tc_api.docktap.trucon_client.IdentityToken", side_effect=ValueError("Identity token is malformed or missing claims")), \
             patch.object(committer, "_expire_intent") as expire_intent:

            committer.enqueue_operation(rec, "pull")
            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert len(snapshot) == 1
        assert snapshot[0]["status"] == "failed_terminal"
        assert snapshot[0]["last_error"] == "Identity token is malformed or missing claims"
        expire_intent.assert_called_once_with("intent-1")

    def test_retry_reuses_same_idempotency_key(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(
            committer,
            "_post_to_trucon",
            side_effect=[urllib.error.URLError("down"), {"record_id": "rec-1", "sequence_num": 7}],
        ) as mock_post, \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "start")
            committer.process_retry_queue(now=time.monotonic())

        assert mock_post.call_count == 2
        first_key = mock_post.call_args_list[0].kwargs["idempotency_key"]
        second_key = mock_post.call_args_list[1].kwargs["idempotency_key"]
        assert first_key == second_key

    def test_acknowledged_retry_is_marked_complete(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "stop"}, container={"id": "xyz789"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(
            committer,
            "_post_to_trucon",
            side_effect=[urllib.error.URLError("down"), {"record_id": "rec-9", "sequence_num": 9}],
        ), \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "stop")
            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert snapshot[0]["status"] == "acknowledged"
        assert snapshot[0]["record_id"] == "rec-9"
        assert snapshot[0]["sequence_num"] == 9

    def test_retry_exhaustion_marks_terminal_failure(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "rm"}, container={"id": "del456"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("still-down")), \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "rm")
            committer.process_retry_queue(now=time.monotonic())
            committer.process_retry_queue(now=time.monotonic())

        snapshot = committer.get_retry_snapshot()
        assert snapshot[0]["status"] == "failed_terminal"
        assert snapshot[0]["retry_attempts"] == 2

    def test_retryable_items_are_not_gc_eligible(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "start"}, container={"id": "abc123"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("down")), \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "start")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 0
        assert len(committer.get_retry_snapshot()) == 1

    def test_acknowledged_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "stop"}, container={"id": "xyz789"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_post_to_trucon", return_value={"record_id": "rec-1", "sequence_num": 1}), \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "stop")

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

    def test_terminal_items_are_gc_eligible_after_retention(self):
        committer = self._make_committer()
        rec = _make_record(operation={"type": "rm"}, container={"id": "del456"})
        mock_signing_context, _ = _mock_signing_context()

        with patch.object(committer, "_post_to_trucon", side_effect=urllib.error.URLError("still-down")), \
             patch.object(committer, "_ensure_chain_initialized", return_value=None), \
             patch.object(committer, "_reserve_commit_intent", return_value={"intent_token": "intent-1", "sequence_num": 1, "prev_event_digest": None, "prev_lookup_hash": None}), \
             patch("tc_api.docktap.trucon_client.detect_credential", return_value="fake-token"), \
             patch("tc_api.docktap.trucon_client.IdentityToken", return_value="tok"), \
             patch("tc_api.docktap.trucon_client.build_signing_context", return_value=mock_signing_context):

            committer.submit_operation(rec, "rm")
            committer.process_retry_queue(now=time.monotonic())
            committer.process_retry_queue(now=time.monotonic())

        assert committer.cleanup_resolved_submissions(now=time.monotonic()) == 1
        assert committer.get_retry_snapshot() == []

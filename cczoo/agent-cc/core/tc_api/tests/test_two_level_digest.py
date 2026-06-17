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
Tests for the two-level-digest-hashing change.

Covers:
- 3.1 compute_entry_digest determinism
- 3.2 compute_event_digest determinism
- 3.3 Entry order sensitivity
- 3.4 Empty entries list
- 3.5 Two-level vs single-level produces different digests
- 3.6 commit_record() predicate structure and digest consistency
"""

import hashlib
from unittest.mock import MagicMock, patch

from tc_api.transparency.commit_client import TrustedLogAPI
from tlog.digest import canonical_json, compute_entry_digest, compute_event_digest
from tlog.types import Entry


# ---------------------------------------------------------------------------
# 3.1 compute_entry_digest determinism
# ---------------------------------------------------------------------------

class TestComputeEntryDigest:
    def test_returns_sha384_prefixed_hex(self):
        result = compute_entry_digest("image_hash", "sha256:abc123")
        assert result.startswith("sha384:")
        hex_part = result.removeprefix("sha384:")
        assert len(hex_part) == 96
        # Verify it's valid hex
        int(hex_part, 16)

    def test_deterministic(self):
        d1 = compute_entry_digest("key1", "value1")
        d2 = compute_entry_digest("key1", "value1")
        assert d1 == d2

    def test_different_key_different_digest(self):
        d1 = compute_entry_digest("key_a", "same_value")
        d2 = compute_entry_digest("key_b", "same_value")
        assert d1 != d2

    def test_different_value_different_digest(self):
        d1 = compute_entry_digest("same_key", "value_a")
        d2 = compute_entry_digest("same_key", "value_b")
        assert d1 != d2

    def test_matches_manual_computation(self):
        key, value = "image_hash", "sha256:abc123"
        expected_payload = canonical_json({"key": key, "value": value})
        expected = "sha384:" + hashlib.sha384(expected_payload.encode("utf-8")).hexdigest()
        assert compute_entry_digest(key, value) == expected


# ---------------------------------------------------------------------------
# 3.2 compute_event_digest determinism
# ---------------------------------------------------------------------------

class TestComputeEventDigest:
    def test_returns_sha384_prefixed_hex(self):
        result = compute_event_digest("evt-1", "build", "2026-01-01T00:00:00", ["sha384:" + "aa" * 48])
        assert result.startswith("sha384:")
        hex_part = result.removeprefix("sha384:")
        assert len(hex_part) == 96

    def test_deterministic(self):
        args = ("evt-1", "build", "2026-01-01T00:00:00", ["sha384:" + "aa" * 48])
        d1 = compute_event_digest(*args)
        d2 = compute_event_digest(*args)
        assert d1 == d2

    def test_matches_manual_computation(self):
        event_id = "evt-1"
        event_type = "build"
        created = "2026-01-01T00:00:00"
        entry_digests = ["sha384:" + "aa" * 48]
        expected_payload = canonical_json({
            "created": created,
            "entry_digests": entry_digests,
            "event_id": event_id,
            "event_type": event_type,
        })
        expected = "sha384:" + hashlib.sha384(expected_payload.encode("utf-8")).hexdigest()
        assert compute_event_digest(event_id, event_type, created, entry_digests) == expected


# ---------------------------------------------------------------------------
# 3.3 Entry order sensitivity
# ---------------------------------------------------------------------------

class TestEntryOrderSensitivity:
    def test_swapped_entries_produce_different_event_digest(self):
        ed1 = compute_entry_digest("key_a", "val_a")
        ed2 = compute_entry_digest("key_b", "val_b")
        created = "2026-01-01T00:00:00"

        digest_ab = compute_event_digest("evt-1", "build", created, [ed1, ed2])
        digest_ba = compute_event_digest("evt-1", "build", created, [ed2, ed1])
        assert digest_ab != digest_ba


# ---------------------------------------------------------------------------
# 3.4 Empty entries list
# ---------------------------------------------------------------------------

class TestEmptyEntries:
    def test_empty_entries_produces_valid_digest(self):
        result = compute_event_digest("evt-1", "build", "2026-01-01T00:00:00", [])
        assert result.startswith("sha384:")
        assert len(result.removeprefix("sha384:")) == 96

    def test_empty_entries_deterministic(self):
        args = ("evt-1", "build", "2026-01-01T00:00:00", [])
        assert compute_event_digest(*args) == compute_event_digest(*args)


# ---------------------------------------------------------------------------
# 3.5 Two-level vs single-level produces different digests
# ---------------------------------------------------------------------------

class TestTwoLevelDiffers:
    def test_two_level_differs_from_single_level(self):
        """Same entries, but single-level (raw entries in hash) vs two-level (entry digests in hash)."""
        entries = [("image_hash", "sha256:abc"), ("sbom_format", "spdx")]
        event_id = "evt-1"
        event_type = "build"
        created = "2026-01-01T00:00:00"

        # Single-level: old algorithm — hash raw entries directly
        single_level_payload = canonical_json({
            "event_id": event_id,
            "event_type": event_type,
            "created": created,
            "entries": [{"key": k, "value": v} for k, v in entries],
        })
        single_level_digest = "sha384:" + hashlib.sha384(single_level_payload.encode("utf-8")).hexdigest()

        # Two-level: new algorithm
        entry_digests = [compute_entry_digest(k, v) for k, v in entries]
        two_level_digest = compute_event_digest(event_id, event_type, created, entry_digests)

        assert single_level_digest != two_level_digest


# ---------------------------------------------------------------------------
# 3.6 Integration: commit_record() predicate structure
# ---------------------------------------------------------------------------

class TestCommitRecordPredicate:
    """Test that commit_record() builds the predicate with two-level digest."""

    @patch("tc_api.transparency.commit_client.IdentityToken")
    @patch("tc_api.transparency.commit_client.build_signing_context")
    def test_predicate_contains_entries_and_entry_digests(self, mock_build_signing_context, mock_identity_token):
        """commit_record() predicate has entries, entry_digests, and digest keys."""
        # Capture the predicate passed to StatementBuilder
        captured_predicate = {}

        mock_token_instance = MagicMock()
        mock_identity_token.return_value = mock_token_instance

        mock_bundle = MagicMock()
        mock_bundle.to_json.return_value = '{"mock": "bundle"}'
        mock_signer = MagicMock()
        mock_signer.sign_dsse.return_value = mock_bundle
        mock_signer.__enter__ = MagicMock(return_value=mock_signer)
        mock_signer.__exit__ = MagicMock(return_value=False)
        mock_ctx = MagicMock()
        mock_ctx.signer.return_value = mock_signer
        mock_build_signing_context.return_value = mock_ctx

        api = TrustedLogAPI(trucon_url="http://localhost:9999")

        def fake_reserve(chain_id, idempotency_key=None, is_baseline=False):
            return {
                "intent_token": "intent-1",
                "chain_id": chain_id,
                "sequence_num": 1,
                "prev_event_digest": None,
                "prev_lookup_hash": None,
                "committed": False,
            }

        # Patch _post_to_trucon to capture and return mock
        def fake_post(**kwargs):
            return {"record_id": "r-1", "mr_value": "aa" * 48, "prev_mr_value": None}
        api._post_to_trucon = MagicMock(side_effect=fake_post)
        api._reserve_commit_intent = MagicMock(side_effect=fake_reserve)

        # Patch StatementBuilder to capture predicate
        class CapturingBuilder:
            def __init__(self):
                self._subjects = []
                self._predicate_type = None
                self._predicate = None

            def subjects(self, s):
                self._subjects = s
                return self

            def predicate_type(self, pt):
                self._predicate_type = pt
                return self

            def predicate(self, p):
                captured_predicate.update(p)
                self._predicate = p
                return self

            def build(self):
                return MagicMock()

        with patch("tc_api.transparency.commit_client.StatementBuilder", CapturingBuilder), patch.object(
            TrustedLogAPI,
            "init_chain",
            autospec=True,
            return_value={"record_id": "baseline", "sequence_num": 1},
        ):
            ctx = api.init_record(context={"chain_ref": "test-chain"})
            api.add_entry(ctx.record_id, Entry(key="image_hash", value="sha256:abc"))
            api.add_entry(ctx.record_id, Entry(key="sbom_format", value="spdx"))
            api.commit_record(
                ctx.record_id,
                event_type="build",
                commit_options={"identity_token": "mock-token"},
            )

        # Verify predicate structure
        assert "entries" in captured_predicate
        assert "entry_digests" in captured_predicate
        assert "digest" in captured_predicate
        assert len(captured_predicate["entries"]) == 2
        assert len(captured_predicate["entry_digests"]) == 2

        # Verify each entry_digest matches compute_entry_digest
        for i, entry in enumerate(captured_predicate["entries"]):
            expected = compute_entry_digest(entry["key"], entry["value"])
            assert captured_predicate["entry_digests"][i] == expected

        # Verify digest matches compute_event_digest
        expected_digest = compute_event_digest(
            captured_predicate["event_id"],
            captured_predicate["event_type"],
            captured_predicate["created"],
            captured_predicate["entry_digests"],
        )
        assert captured_predicate["digest"] == expected_digest

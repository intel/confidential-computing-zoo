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

"""Tests for submit_operation delegation signing path in TruConCommitter."""
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from tc_api.docktap.trucon_client import TruConCommitter


@pytest.fixture()
def committer():
    return TruConCommitter(
        trucon_url="http://127.0.0.1:59999",
        start_retry_worker=False,
    )


def _mock_op_record():
    """Minimal op_record mock with required attributes."""
    record = MagicMock()
    record.image = {"name": "test-image", "digest": "sha256:abc"}
    record.container = {"name": "test-ctr", "id": "ctr-123"}
    record.operation = "pull"
    record.runtime_engine = "docker"
    record.labels = {}
    record.status_code = 200
    record.response = {"status": 200}
    return record


def _future_iso(seconds=3600):
    return (datetime.utcnow() + timedelta(seconds=seconds)).isoformat()


class TestDelegationSigningPath:
    @patch.dict("os.environ", {"DOCKTAP_AUTH_MODE": "explicit_delegation"}, clear=False)
    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value="header.payload.signature")
    @patch("tc_api.docktap.trucon_client.get_chain_owner_private_key")
    def test_explicit_delegation_mode_prefers_delegation_even_with_token(
        self, mock_get_key, _mock_token, committer
    ):
        mock_key = ec.generate_private_key(ec.SECP384R1())
        mock_get_key.return_value = mock_key

        delegation = {
            "delegation_id": "del-explicit-001",
            "chain_id": "docktap-runtime",
            "scope": ["pull", "create", "start", "stop", "rm"],
            "expires_at": _future_iso(),
            "signer_identity": "user@example.com",
            "sequence_num": 2,
        }

        with patch("tc_api.trucon.database.get_active_delegation", return_value=delegation), \
             patch.object(committer, "_resolve_submission_context", return_value=("docktap-runtime", "wl-1", "l-1", "inst-1")), \
             patch.object(committer, "_reserve_commit_intent", return_value={
                 "sequence_num": 3,
                 "prev_event_digest": "sha384:prev",
                 "prev_lookup_hash": "sha384:lh",
                 "intent_token": "tok-abc",
             }), \
             patch("tc_api.docktap.trucon_client.sign_dsse_with_owner_key") as mock_sign, \
             patch("tc_api.docktap.trucon_client.generate_chain_owner_pub_key_pem", return_value="PEM"), \
             patch("tc_api.docktap.trucon_client.SigstoreLogAdapter") as mock_adapter_cls, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "r-1", "sequence_num": 3}), \
             patch.object(committer, "_mark_acknowledged"), \
             patch("tc_api.docktap.trucon_client.IdentityToken") as mock_identity_token:

            mock_sign.return_value = {
                "payloadType": "application/vnd.in-toto+json",
                "payload": "cGF5bG9hZA==",
                "signatures": [{"sig": "c2ln"}],
            }
            mock_adapter_cls.return_value.submit_owner_signed_entry.return_value = (
                "uuid-123", 999, {"logIndex": 999}
            )

            result = committer._do_submit(_mock_op_record(), "pull")

            assert result is True
            mock_sign.assert_called_once()
            mock_identity_token.assert_not_called()

    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value=None)
    @patch("tc_api.docktap.trucon_client.get_chain_owner_private_key")
    def test_delegation_path_invoked_when_no_token(
        self, mock_get_key, _mock_token, committer
    ):
        """When no OIDC token and delegation exists, owner key signing path is used."""
        mock_key = ec.generate_private_key(ec.SECP384R1())
        mock_get_key.return_value = mock_key

        delegation = {
            "delegation_id": "del-test-001",
            "chain_id": "docktap-runtime",
            "scope": ["pull", "create", "start", "stop", "rm"],
            "expires_at": _future_iso(),
            "signer_identity": "user@example.com",
            "sequence_num": 2,
        }

        with patch("tc_api.trucon.database.get_active_delegation", return_value=delegation), \
             patch.object(committer, "_resolve_submission_context", return_value=("docktap-runtime", "wl-1", "l-1", "inst-1")), \
             patch.object(committer, "_reserve_commit_intent", return_value={
                 "sequence_num": 3,
                 "prev_event_digest": "sha384:prev",
                 "prev_lookup_hash": "sha384:lh",
                 "intent_token": "tok-abc",
             }), \
             patch("tc_api.docktap.trucon_client.sign_dsse_with_owner_key") as mock_sign, \
             patch("tc_api.docktap.trucon_client.generate_chain_owner_pub_key_pem", return_value="PEM"), \
             patch("tc_api.docktap.trucon_client.SigstoreLogAdapter") as mock_adapter_cls, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "r-1", "sequence_num": 3}), \
             patch.object(committer, "_mark_acknowledged"):

            mock_sign.return_value = {
                "payloadType": "application/vnd.in-toto+json",
                "payload": "cGF5bG9hZA==",
                "signatures": [{"sig": "c2ln"}],
            }
            mock_adapter_cls.return_value.submit_owner_signed_entry.return_value = (
                "uuid-123", 999, {"logIndex": 999}
            )

            op_record = _mock_op_record()
            result = committer._do_submit(op_record, "pull")

            assert result is True
            mock_sign.assert_called_once()
            mock_adapter_cls.return_value.submit_owner_signed_entry.assert_called_once()

    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value=None)
    def test_raises_when_no_token_and_no_delegation(self, _mock_token, committer):
        """When no token and no delegation, MissingIdentityTokenError is raised."""
        from tc_api.docktap.trucon_client import MissingIdentityTokenError

        with patch("tc_api.trucon.database.get_active_delegation", return_value=None), \
             patch.object(committer, "_resolve_submission_context", return_value=("chain-x", "w", "l", "i")):

            op_record = _mock_op_record()
            with pytest.raises(MissingIdentityTokenError):
                committer._do_submit(op_record, "pull")

    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value=None)
    def test_scope_violation_raises(self, _mock_token, committer):
        """When delegation scope doesn't include operation, error is raised."""
        from tc_api.docktap.trucon_client import MissingIdentityTokenError

        delegation = {
            "delegation_id": "del-2",
            "chain_id": "chain-y",
            "scope": ["pull", "create"],  # no "rm"
            "expires_at": _future_iso(),
        }

        with patch("tc_api.trucon.database.get_active_delegation", return_value=delegation), \
             patch.object(committer, "_resolve_submission_context", return_value=("chain-y", "w", "l", "i")):

            op_record = _mock_op_record()
            with pytest.raises(MissingIdentityTokenError, match="scope"):
                committer._do_submit(op_record, "rm")

    @patch("tc_api.docktap.trucon_client._resolve_identity_token_str", return_value=None)
    @patch("tc_api.docktap.trucon_client.get_chain_owner_private_key")
    def test_delegation_id_in_predicate(self, mock_get_key, _mock_token, committer):
        """When delegation path is used, delegation_id appears in predicate."""
        mock_key = ec.generate_private_key(ec.SECP384R1())
        mock_get_key.return_value = mock_key

        delegation = {
            "delegation_id": "del-pred-check",
            "chain_id": "chain-z",
            "scope": ["pull"],
            "expires_at": _future_iso(),
        }

        captured_statement = {}

        def capture_sign(statement_json, key):
            captured_statement["json"] = statement_json
            return {
                "payloadType": "application/vnd.in-toto+json",
                "payload": "cGF5bG9hZA==",
                "signatures": [{"sig": "c2ln"}],
            }

        with patch("tc_api.trucon.database.get_active_delegation", return_value=delegation), \
             patch.object(committer, "_resolve_submission_context", return_value=("chain-z", "w", "l", "i")), \
             patch.object(committer, "_reserve_commit_intent", return_value={
                 "sequence_num": 4, "prev_event_digest": None, "prev_lookup_hash": None, "intent_token": "t",
             }), \
             patch("tc_api.docktap.trucon_client.sign_dsse_with_owner_key", side_effect=capture_sign), \
             patch("tc_api.docktap.trucon_client.generate_chain_owner_pub_key_pem", return_value="PEM"), \
             patch("tc_api.docktap.trucon_client.SigstoreLogAdapter") as mock_adapter_cls, \
             patch.object(committer, "_post_to_trucon", return_value={"record_id": "r-2"}), \
             patch.object(committer, "_mark_acknowledged"):

            mock_adapter_cls.return_value.submit_owner_signed_entry.return_value = ("u", 1, {})

            committer._do_submit(_mock_op_record(), "pull")

            statement = json.loads(captured_statement["json"])
            assert statement["predicate"]["delegation_id"] == "del-pred-check"

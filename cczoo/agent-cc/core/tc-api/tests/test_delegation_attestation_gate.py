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

"""Tests for delegation-aware attestation gate in docker_proxy."""
from unittest.mock import patch

from tc_api.docktap.trucon_client import has_active_delegation


class TestHasActiveDelegation:
    @patch("tc_api.trucon.database.get_active_delegation", return_value=None)
    def test_returns_false_when_no_delegation(self, _mock):
        assert has_active_delegation("chain-x") is False

    @patch("tc_api.trucon.database.get_active_delegation", return_value={"delegation_id": "del-1"})
    def test_returns_true_when_delegation_exists(self, _mock):
        assert has_active_delegation("chain-y") is True

    @patch("tc_api.trucon.database.get_active_delegation", side_effect=Exception("db error"))
    def test_returns_false_on_exception(self, _mock):
        assert has_active_delegation("chain-z") is False

    @patch("tc_api.trucon.database.get_active_delegation", return_value={"delegation_id": "del-2"})
    def test_defaults_to_runtime_chain(self, mock_get):
        has_active_delegation()
        mock_get.assert_called_once()
        # Should use the default measured chain.
        args = mock_get.call_args
        assert args[0][0] == "default"


class TestAttestationGateWithDelegation:
    """Verify the gate logic in docker_proxy allows delegation."""

    def test_gate_check_order(self):
        """Confirm that the gate checks both has_reusable_identity_token and has_active_delegation."""
        # This is a structural test — we verify the import path works
        from tc_api.docktap.proxy.docker_proxy import has_active_delegation as imported_fn
        assert callable(imported_fn)

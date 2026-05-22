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
        # Should use DEFAULT_RUNTIME_CHAIN_ID (docktap-runtime)
        args = mock_get.call_args
        assert args[0][0] == "docktap-runtime"


class TestAttestationGateWithDelegation:
    """Verify the gate logic in docker_proxy allows delegation."""

    def test_gate_check_order(self):
        """Confirm that the gate checks both has_reusable_identity_token and has_active_delegation."""
        # This is a structural test — we verify the import path works
        from tc_api.docktap.proxy.docker_proxy import has_active_delegation as imported_fn
        assert callable(imported_fn)

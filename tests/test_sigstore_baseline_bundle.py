from unittest.mock import MagicMock, patch

from tc_api.sigstore_baseline import build_baseline_sigstore_bundle


@patch("tc_api.sigstore_baseline.IdentityToken")
@patch("tc_api.sigstore_baseline.SigningContext")
def test_build_baseline_sigstore_bundle_contains_replay_fields(mock_signing_ctx, mock_identity_token):
    captured_predicate = {}

    mock_bundle = MagicMock()
    mock_bundle.to_json.return_value = '{"mock":"bundle"}'
    mock_signer = MagicMock()
    mock_signer.sign_dsse.return_value = mock_bundle
    mock_signer.__enter__ = MagicMock(return_value=mock_signer)
    mock_signer.__exit__ = MagicMock(return_value=False)
    mock_ctx = MagicMock()
    mock_ctx.signer.return_value = mock_signer
    mock_signing_ctx.production.return_value = mock_ctx

    class CapturingBuilder:
        def __init__(self):
            self._predicate = None

        def subjects(self, subjects):
            return self

        def predicate_type(self, predicate_type):
            return self

        def predicate(self, predicate):
            captured_predicate.update(predicate)
            self._predicate = predicate
            return self

        def build(self):
            return MagicMock()

    with patch("tc_api.sigstore_baseline.StatementBuilder", CapturingBuilder):
        bundle_json, pub_key_pem, event_digest = build_baseline_sigstore_bundle(
            chain_id="default",
            rtmr_value="11" * 48,
            ccel_digest="sha384:" + ("22" * 48),
            ccel_eventlog_b64="Zm9v",
            identity_token_str="mock-token",
        )

    assert bundle_json == '{"mock":"bundle"}'
    assert pub_key_pem.startswith("-----BEGIN PUBLIC KEY-----")
    assert event_digest.startswith("sha384:")
    assert captured_predicate["event_id"] == "evt-log0-default"
    assert captured_predicate["event_type"] == "chain.init"
    assert captured_predicate["digest"] == event_digest
    assert len(captured_predicate["entry_digests"]) == 3
    assert any(entry["key"] == "baseline_rtmr" for entry in captured_predicate["entries"])
    assert any(entry["key"] == "ccel_eventlog_b64" and entry["value"] == "Zm9v" for entry in captured_predicate["entries"])
    assert any(entry["key"] == "pub_key" and entry["value"] == pub_key_pem for entry in captured_predicate["entries"])
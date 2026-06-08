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

import pytest
import io
import urllib.error
from unittest.mock import patch

from tc_api.transparency.commit_client import TrustedLogAPI


class _ImmutableLog:
    rekor_url = "https://rekor.sigstore.dev"


def test_init_chain_uses_active_identity_token_for_baseline_signing():
    captured = {}
    responses = [
        {
            "init_token": "init-123",
            "rtmr_value": "aa" * 48,
            "ccel_digest": "sha384:" + ("bb" * 48),
            "ccel_eventlog_b64": "Zm9v",
        },
        {
            "record_id": "rec-123",
            "sequence_num": 1,
        },
    ]

    def fake_request_json(method, path, **kwargs):
        assert responses, f"Unexpected request {method} {path}"
        return responses.pop(0)

    def fake_build_baseline_sigstore_bundle(**kwargs):
        captured.update(kwargs)
        return '{"mock":"bundle"}', 'test-pub-key', 'sha384:' + ('11' * 48)

    tlog = TrustedLogAPI(immutable_log=_ImmutableLog())

    with patch("tc_api.transparency.commit_client.request_json", side_effect=fake_request_json), \
         patch.object(tlog, "_reserve_commit_intent", return_value={
             "intent_token": "intent-123",
             "sequence_num": 1,
             "prev_event_digest": None,
             "prev_lookup_hash": None,
         }), \
         patch("tc_api.transparency.commit_client.build_baseline_sigstore_bundle", side_effect=fake_build_baseline_sigstore_bundle):
        result = tlog.init_chain("tc-api-service", identity_token_str="active-token-123")

    assert result == {"record_id": "rec-123", "sequence_num": 1}
    assert captured["identity_token_str"] == "active-token-123"
    assert captured["chain_id"] == "default"


def test_init_chain_raises_when_baseline_bundle_cannot_be_built():
    responses = [
        {
            "init_token": "init-123",
            "rtmr_value": "aa" * 48,
            "ccel_digest": "sha384:" + ("bb" * 48),
            "ccel_eventlog_b64": "Zm9v",
        },
    ]

    def fake_request_json(method, path, **kwargs):
        assert responses, f"Unexpected request {method} {path}"
        return responses.pop(0)

    tlog = TrustedLogAPI(immutable_log=_ImmutableLog())

    with patch("tc_api.transparency.commit_client.request_json", side_effect=fake_request_json), \
         patch.object(tlog, "_reserve_commit_intent", return_value={
             "intent_token": "intent-123",
             "sequence_num": 1,
             "prev_event_digest": None,
             "prev_lookup_hash": None,
         }), \
         patch(
             "tc_api.transparency.commit_client.build_baseline_sigstore_bundle",
             side_effect=RuntimeError("missing token"),
         ):
        with pytest.raises(RuntimeError, match="Failed to build baseline Sigstore bundle"):
            tlog.init_chain("tc-api-service", identity_token_str="active-token-123")


def test_init_chain_surfaces_trucon_http_error_detail():
    responses = [
        {
            "init_token": "init-123",
            "rtmr_value": "aa" * 48,
            "ccel_digest": "sha384:" + ("bb" * 48),
            "ccel_eventlog_b64": "Zm9v",
        },
    ]

    def fake_request_json(method, path, **kwargs):
        if path == "/init-chain/default/baseline":
            return responses.pop(0)
        raise urllib.error.HTTPError(
            url=path,
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"detail":"Quote adapter is unavailable"}'),
        )

    tlog = TrustedLogAPI(immutable_log=_ImmutableLog())

    with patch("tc_api.transparency.commit_client.request_json", side_effect=fake_request_json), \
         patch.object(tlog, "_reserve_commit_intent", return_value={
             "intent_token": "intent-123",
             "sequence_num": 1,
             "prev_event_digest": None,
             "prev_lookup_hash": None,
         }), \
         patch("tc_api.transparency.commit_client.build_baseline_sigstore_bundle", return_value=(
             '{"mock":"bundle"}',
             "test-pub-key",
             "sha384:" + ("11" * 48),
         )):
        with pytest.raises(RuntimeError, match="Quote adapter is unavailable"):
            tlog.init_chain("tc-api-service", identity_token_str="active-token-123")
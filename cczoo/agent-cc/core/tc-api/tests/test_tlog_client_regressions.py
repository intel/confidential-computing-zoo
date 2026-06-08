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

from unittest.mock import patch

from tlog.types import Entry
from tc_api.transparency.commit_client import TrustedLogAPI


def test_commit_record_lazily_initializes_default_chain_before_reserving_intent():
    api = TrustedLogAPI(immutable_log=None, trucon_url="http://example.invalid")
    ctx = api.init_record(context={"chain_ref": "default"})
    api.add_entry(ctx.record_id, Entry(key="k", value="v"))

    calls = []

    with patch("tc_api.transparency.commit_client.get_chain_state", return_value=None), patch.object(
        TrustedLogAPI,
        "init_chain",
        autospec=True,
        side_effect=lambda self, chain_id="default", identity_token_str=None: calls.append(("init_chain", chain_id))
        or {"record_id": "baseline", "sequence_num": 1},
    ), patch.object(
        TrustedLogAPI,
        "_reserve_commit_intent",
        autospec=True,
        side_effect=lambda self, chain_id, idempotency_key=None, is_baseline=False: calls.append(
            ("reserve", chain_id, is_baseline)
        )
        or {
            "intent_token": "tok",
            "sequence_num": 2,
            "prev_event_digest": "sha384:" + ("0" * 96),
            "prev_lookup_hash": "sha384:" + ("1" * 96),
            "committed": True,
            "record_id": "rid",
        },
    ):
        result = api.commit_record(
            record_id=ctx.record_id,
            event_type="build",
            commit_options={"identity_token": "a.b.c"},
        )

    assert result.record_id == "rid"
    assert calls == [
        ("init_chain", "default"),
        ("reserve", "default", False),
    ]
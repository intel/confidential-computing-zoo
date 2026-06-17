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

import importlib
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tc_api.trucon.database import init_db, insert_record, update_chain_state, update_record_confirmed
from tests.utils import StaticQuoteAdapter, make_db_patches

trucon_app_mod = importlib.import_module("tc_api.trucon.app")
trucon_db_mod = importlib.import_module("tc_api.trucon.database")


@pytest.fixture
def trucon_client(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    patches = make_db_patches(
        trucon_db_mod,
        db_path,
        ["get_chain_state", "get_latest_confirmed_record"],
    )

    old_auth = trucon_app_mod._AUTH_DISABLED
    old_quote_adapter = trucon_app_mod._quote_adapter

    try:
        trucon_app_mod._AUTH_DISABLED = True
        trucon_app_mod._quote_adapter = None

        with patch.object(trucon_app_mod, "acquire_instance_lock"), \
             patch.object(trucon_app_mod, "release_instance_lock"), \
             patch.object(trucon_app_mod, "_crash_recovery"), \
             patch.object(trucon_app_mod, "_submit_daemon_loop"), \
             patch.object(trucon_app_mod, "init_db"), \
             patch.object(trucon_app_mod, "SigstoreLogAdapter"), \
             patch.object(trucon_app_mod, "TdxQuoteAdapter", return_value=trucon_app_mod._quote_adapter), \
             patch.object(trucon_app_mod, "get_chain_state", side_effect=patches["get_chain_state"]), \
             patch.object(trucon_app_mod, "get_latest_confirmed_record", side_effect=patches["get_latest_confirmed_record"]):
            client = TestClient(trucon_app_mod.app, raise_server_exceptions=False)
            yield client, db_path
    finally:
        trucon_app_mod._AUTH_DISABLED = old_auth
        trucon_app_mod._quote_adapter = old_quote_adapter


def _insert_confirmed_record(db_path: str, chain_id: str, sequence_num: int, log_id: str, mr_value: str, event_digest: str | None = None):
    record_id = f"rec-{sequence_num}"
    insert_record(
        record_id=record_id,
        event_id=f"evt-{sequence_num}",
        payload={"bundle": "test", "chain_id": chain_id},
        status="PENDING",
        chain_id=chain_id,
        rtmr_extended=True,
        prev_log_id=None,
        mr_value=mr_value,
        sequence_num=sequence_num,
        event_digest=event_digest,
        db_path=db_path,
    )
    update_record_confirmed(record_id, log_id, db_path=db_path)
    update_chain_state(
        chain_id=chain_id,
        head_record_id=record_id,
        sequence_num=sequence_num,
        mr_value=mr_value,
        head_log_id=log_id,
        db_path=db_path,
    )


def test_evidence_export_success_returns_latest_confirmed_head(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48, "sha384:" + "11" * 48)
    _insert_confirmed_record(db_path, "default", 2, "log-2", "bb" * 48, "sha384:" + "22" * 48)
    update_chain_state(chain_id="default", head_record_id="rec-3", sequence_num=3, mr_value="cc" * 48, db_path=db_path)

    expected_value = trucon_app_mod.compute_binding_expected_value("default", 2, "log-2", "bb" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value)

    response = client.get("/evidence")

    assert response.status_code == 200
    data = response.json()
    assert data["sequence_num"] == 2
    assert data["head_log_id"] == "log-2"
    assert data["mr_value"] == "bb" * 48
    assert data["report_data_binding"]["expected_value"] == expected_value


def test_evidence_export_fails_without_confirmed_head(trucon_client):
    client, db_path = trucon_client
    update_chain_state(chain_id="default", head_record_id="rec-pending", sequence_num=1, mr_value="aa" * 48, db_path=db_path)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter("head_log_id_bytes:" + "11" * 8)

    response = client.get("/evidence")

    assert response.status_code == 409
    assert "no confirmed immutable-log head" in response.json()["detail"]


def test_evidence_export_fails_when_quote_acquisition_fails(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    expected_value = trucon_app_mod.compute_binding_expected_value("default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter(expected_value, should_fail=True)

    response = client.get("/evidence")

    assert response.status_code == 500
    assert "Quote acquisition failed" in response.json()["detail"]


def test_evidence_export_fails_on_binding_mismatch(trucon_client):
    client, db_path = trucon_client
    _insert_confirmed_record(db_path, "default", 1, "log-1", "aa" * 48)
    trucon_app_mod._quote_adapter = StaticQuoteAdapter("head_log_id_bytes:" + "ff" * 8)

    response = client.get("/evidence")

    assert response.status_code == 500
    assert "report data did not match" in response.json()["detail"]
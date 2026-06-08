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

"""Unit tests for workload label extraction and chain routing logic."""

import json

import pytest

from tc_api.docktap.proxy.docker_proxy import DockerProxyServer, WORKLOAD_LABEL, LAUNCH_LABEL
from tc_api.docktap.trucon_client import TruConCommitter
from tc_api.docktap.proxy.operation_log import OperationRecord
from tc_api.docktap.workload_store import WorkloadStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_create_request(labels=None, image="nginx"):
    """Build a minimal HTTP request bytes for a docker create."""
    body = {"Image": image}
    if labels is not None:
        body["Labels"] = labels
    body_bytes = json.dumps(body).encode()
    request = (
        f"POST /v1.45/containers/create HTTP/1.1\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"\r\n"
    ).encode() + body_bytes
    return request


def _make_record(**overrides) -> OperationRecord:
    defaults = dict(
        operation={"type": "unknown"},
        image={},
        container={},
    )
    defaults.update(overrides)
    return OperationRecord(**defaults)


# ---------------------------------------------------------------------------
# 5.2  _extract_workload_id
# ---------------------------------------------------------------------------

class TestExtractWorkloadId:
    def test_label_present(self):
        req = _make_create_request(labels={WORKLOAD_LABEL: "my-app"})
        assert DockerProxyServer._extract_workload_id(req) == "my-app"

    def test_label_absent(self):
        req = _make_create_request(labels={})
        assert DockerProxyServer._extract_workload_id(req) is None

    def test_no_labels_key(self):
        req = _make_create_request(labels=None)
        assert DockerProxyServer._extract_workload_id(req) is None

    def test_label_empty_string(self):
        req = _make_create_request(labels={WORKLOAD_LABEL: ""})
        assert DockerProxyServer._extract_workload_id(req) is None

    def test_malformed_body(self):
        req = b"POST /v1.45/containers/create HTTP/1.1\r\n\r\nnot-json"
        assert DockerProxyServer._extract_workload_id(req) is None

    def test_other_labels_ignored(self):
        req = _make_create_request(labels={"com.example.foo": "bar"})
        assert DockerProxyServer._extract_workload_id(req) is None

    def test_label_with_other_labels(self):
        req = _make_create_request(labels={
            "com.example.foo": "bar",
            WORKLOAD_LABEL: "prod-svc",
        })
        assert DockerProxyServer._extract_workload_id(req) == "prod-svc"

    def test_extract_launch_id(self):
        req = _make_create_request(labels={LAUNCH_LABEL: "launch-123"})
        assert DockerProxyServer._extract_launch_id(req) == "launch-123"


# ---------------------------------------------------------------------------
# 5.3  Chain routing integration
# ---------------------------------------------------------------------------

class TestChainRouting:
    @pytest.fixture
    def store(self, tmp_path):
        s = WorkloadStore(db_path=str(tmp_path / "map.db"))
        s.init_db()
        return s

    def test_create_with_label_routes_to_workload_chain(self, store):
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "create"},
            container={"id": "abc123", "name": "myc"},
        )
        chain = committer._resolve_chain_id(rec, "create", workload_id="my-app")
        assert chain == "default"
        # Mapping should be persisted
        assert store.get("abc123") == "my-app"

    def test_create_without_label_defaults(self, store):
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "create"},
            container={"id": "abc123"},
        )
        chain = committer._resolve_chain_id(rec, "create", workload_id=None)
        assert chain == "default"
        assert store.get("abc123") is None

    def test_start_resolves_from_store(self, store):
        store.put("abc123", "my-app")
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "abc123"},
        )
        chain = committer._resolve_chain_id(rec, "start", workload_id=None)
        assert chain == "default"

    def test_stop_resolves_from_store(self, store):
        store.put("abc123", "my-app")
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "stop"},
            container={"id": "abc123"},
        )
        chain = committer._resolve_chain_id(rec, "stop", workload_id=None)
        assert chain == "default"

    def test_rm_resolves_from_store(self, store):
        store.put("abc123", "my-app")
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "rm"},
            container={"id": "abc123"},
        )
        chain = committer._resolve_chain_id(rec, "rm", workload_id=None)
        assert chain == "default"

    def test_start_no_mapping_defaults(self, store):
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "unknown"},
        )
        chain = committer._resolve_chain_id(rec, "start", workload_id=None)
        assert chain == "default"

    def test_pull_uses_runtime_chain(self, store):
        committer = TruConCommitter(workload_store=store)
        rec = _make_record(
            operation={"type": "pull"},
            image={"name": "nginx"},
        )
        chain = committer._resolve_chain_id(rec, "pull", workload_id=None)
        assert chain == "default"

    def test_create_persists_then_start_resolves(self, store):
        """Full lifecycle: create with label → start resolves same chain."""
        committer = TruConCommitter(workload_store=store)

        create_rec = _make_record(
            operation={"type": "create"},
            container={"id": "c1", "name": "myc"},
        )
        chain1 = committer._resolve_chain_id(create_rec, "create", workload_id="svc-a")
        assert chain1 == "default"

        start_rec = _make_record(
            operation={"type": "start"},
            container={"id": "c1"},
        )
        chain2 = committer._resolve_chain_id(start_rec, "start", workload_id=None)
        assert chain2 == "default"

    def test_restart_recovery_chain_routing(self, tmp_path):
        """Mapping survives store re-init (Docktap restart simulation)."""
        db_path = str(tmp_path / "map.db")

        store1 = WorkloadStore(db_path=db_path)
        store1.init_db()
        committer1 = TruConCommitter(workload_store=store1)
        rec = _make_record(
            operation={"type": "create"},
            container={"id": "c1"},
        )
        committer1._resolve_chain_id(rec, "create", workload_id="my-app")

        # Simulate restart
        store2 = WorkloadStore(db_path=db_path)
        store2.init_db()
        committer2 = TruConCommitter(workload_store=store2)
        rec2 = _make_record(
            operation={"type": "stop"},
            container={"id": "c1"},
        )
        assert committer2._resolve_chain_id(rec2, "stop", workload_id=None) == "default"

    def test_no_store_defaults_to_default(self):
        """Committer without workload_store still uses the runtime fallback chain."""
        committer = TruConCommitter(workload_store=None)
        rec = _make_record(
            operation={"type": "start"},
            container={"id": "c1"},
        )
        assert committer._resolve_chain_id(rec, "start", workload_id=None) == "default"

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
import tomllib
from pathlib import Path
from unittest.mock import Mock

import pytest

from tc_api.trucon.config import ImmutableBackendConfig, get_immutable_backend_config
from tc_api.trucon.immutable_fanout import CompositeImmutableLogAdapter

trucon_app_mod = importlib.import_module("tc_api.trucon.app")


def test_tlog_pyproject_exposes_rekor_extra():
    pyproject_path = Path(__file__).resolve().parents[2] / "tlog" / "pyproject.toml"

    with pyproject_path.open("rb") as handle:
        pyproject = tomllib.load(handle)

    optional_deps = pyproject["project"]["optional-dependencies"]
    assert "rekor" in optional_deps
    assert "sigstore-rekor-types" in optional_deps["rekor"]


def test_default_immutable_backend_config(monkeypatch):
    monkeypatch.delenv("TC_IMMUTABLE_WRITE_BACKENDS", raising=False)
    monkeypatch.delenv("TC_IMMUTABLE_PRIMARY_BACKEND", raising=False)
    monkeypatch.delenv("TC_IMMUTABLE_WRITE_POLICY", raising=False)
    monkeypatch.delenv("TC_IMMUTABLE_BACKEND", raising=False)

    config = get_immutable_backend_config()

    assert config.write_backends == ("rekor",)
    assert config.primary_backend == "rekor"
    assert config.write_policy == "primary"


def test_onchain_only_config_uses_single_backend_as_primary(monkeypatch):
    monkeypatch.setenv("TC_IMMUTABLE_WRITE_BACKENDS", "onchain")
    monkeypatch.delenv("TC_IMMUTABLE_PRIMARY_BACKEND", raising=False)

    config = get_immutable_backend_config()

    assert config.write_backends == ("onchain",)
    assert config.primary_backend == "onchain"


def test_unknown_immutable_backend_is_rejected(monkeypatch):
    monkeypatch.setenv("TC_IMMUTABLE_WRITE_BACKENDS", "rekor,unknown")

    with pytest.raises(ValueError, match="Unknown immutable backend"):
        get_immutable_backend_config()


def test_placeholder_onchain_fanout_is_rejected(monkeypatch):
    monkeypatch.setenv("TC_IMMUTABLE_WRITE_BACKENDS", "rekor,onchain")

    with pytest.raises(ValueError, match="fanout configuration"):
        get_immutable_backend_config()


def test_load_immutable_adapter_returns_single_backend_instance(monkeypatch):
    monkeypatch.setenv("TC_IMMUTABLE_WRITE_BACKENDS", "rekor")
    rekor_adapter = object()

    def fake_load_backend(name, **kwargs):
        assert kwargs == {"bundle_mirror": None}
        assert name == "rekor"
        return rekor_adapter

    monkeypatch.setattr(trucon_app_mod, "_load_backend_adapter", fake_load_backend)

    adapter = trucon_app_mod._load_immutable_adapter(bundle_mirror=None)

    assert adapter is rekor_adapter


def test_load_immutable_adapter_returns_composite_for_multi_backend_config(monkeypatch):
    rekor_adapter = object()
    onchain_adapter = object()

    monkeypatch.setattr(
        trucon_app_mod,
        "get_immutable_backend_config",
        lambda: ImmutableBackendConfig(
            write_backends=("rekor", "onchain"),
            primary_backend="rekor",
            write_policy="primary",
        ),
    )

    def fake_load_backend(name, **kwargs):
        assert kwargs == {"bundle_mirror": None}
        if name == "rekor":
            return rekor_adapter
        if name == "onchain":
            return onchain_adapter
        raise AssertionError(f"unexpected backend {name}")

    monkeypatch.setattr(trucon_app_mod, "_load_backend_adapter", fake_load_backend)

    adapter = trucon_app_mod._load_immutable_adapter(bundle_mirror=None)

    assert isinstance(adapter, CompositeImmutableLogAdapter)
    assert adapter.primary_backend == "rekor"
    assert adapter.primary_adapter is rekor_adapter
    assert adapter.secondary_adapters == (("onchain", onchain_adapter),)


def test_composite_adapter_preserves_primary_result_and_primary_reads():
    primary = Mock()
    primary.submit_bundle.return_value = ("rekor-log-id", "confirmed", {"uuid": "rekor-uuid"})
    primary.get_entry.return_value = {"entry": "primary"}
    primary.traverse.return_value = [{"entry": 1}]
    primary.find_entries_by_payload_hash.return_value = [{"entry": "hash-match"}]

    secondary = Mock()
    secondary.submit_bundle.return_value = ("side-log-id", "pending", {"uuid": "side-uuid"})

    adapter = CompositeImmutableLogAdapter(
        primary_backend="rekor",
        primary_adapter=primary,
        secondary_adapters=(("mock-secondary", secondary),),
    )

    log_id, status, receipt = adapter.submit_bundle("bundle-json")

    assert (log_id, status, receipt) == ("rekor-log-id", "confirmed", {"uuid": "rekor-uuid"})
    assert adapter.get_entry("rekor-log-id") == {"entry": "primary"}
    assert adapter.traverse("rekor-log-id") == [{"entry": 1}]
    assert adapter.find_entries_by_payload_hash("abc") == [{"entry": "hash-match"}]
    assert adapter.last_submit_results["rekor"]["status"] == "confirmed"
    assert adapter.last_submit_results["mock-secondary"]["status"] == "pending"


def test_composite_adapter_records_secondary_failures_while_preserving_primary_success():
    primary = Mock()
    primary.submit_bundle.return_value = ("rekor-log-id", "confirmed", {"uuid": "rekor-uuid"})

    secondary = Mock()
    secondary.submit_bundle.side_effect = RuntimeError("secondary backend offline")

    adapter = CompositeImmutableLogAdapter(
        primary_backend="rekor",
        primary_adapter=primary,
        secondary_adapters=(("mock-secondary", secondary),),
    )

    assert adapter.submit_bundle("bundle-json") == ("rekor-log-id", "confirmed", {"uuid": "rekor-uuid"})
    assert adapter.last_submit_results["mock-secondary"]["status"] == "error"
    assert "offline" in adapter.last_submit_results["mock-secondary"]["error"]
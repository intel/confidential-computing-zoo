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

"""Unit tests for docktap/workload_store.py"""

import pytest

from tc_api.docktap.workload_store import WorkloadStore


@pytest.fixture
def store(tmp_path):
    """Create a WorkloadStore backed by a temp-dir SQLite file."""
    db_path = str(tmp_path / "container_map.db")
    s = WorkloadStore(db_path=db_path)
    s.init_db()
    return s


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "container_map.db")


class TestWorkloadStore:
    def test_put_and_get(self, store):
        store.put("abc123", "my-app")
        assert store.get("abc123") == "my-app"

    def test_get_missing_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_put_overwrites(self, store):
        store.put("abc123", "app-v1")
        store.put("abc123", "app-v2")
        assert store.get("abc123") == "app-v2"

    def test_multiple_containers(self, store):
        store.put("c1", "app-a")
        store.put("c2", "app-b")
        store.put("c3", "app-a")
        assert store.get("c1") == "app-a"
        assert store.get("c2") == "app-b"
        assert store.get("c3") == "app-a"

    def test_restart_recovery(self, db_path):
        """Data persists across WorkloadStore instances (simulates restart)."""
        s1 = WorkloadStore(db_path=db_path)
        s1.init_db()
        s1.put("abc123", "my-app")

        # Simulate restart — new instance, same db path
        s2 = WorkloadStore(db_path=db_path)
        s2.init_db()
        assert s2.get("abc123") == "my-app"

    def test_init_db_creates_directory(self, tmp_path):
        nested = str(tmp_path / "sub" / "dir" / "map.db")
        s = WorkloadStore(db_path=nested)
        s.init_db()
        s.put("c1", "w1")
        assert s.get("c1") == "w1"

    def test_init_db_idempotent(self, store):
        store.put("c1", "w1")
        store.init_db()  # second call should not lose data
        assert store.get("c1") == "w1"

    def test_metadata_fields_are_recorded(self, store):
        store.put("abc123", "my-app", launch_id="launch-123")
        metadata = store.get_metadata("abc123")

        assert metadata is not None
        assert metadata["workload_id"] == "my-app"
        assert metadata["launch_id"] == "launch-123"
        assert metadata["last_operation"] == "create"
        assert metadata["last_seen_at"] is not None
        assert metadata["removed_at"] is None

    def test_touch_updates_lifecycle_state(self, store):
        store.put("abc123", "my-app")
        store.touch("abc123", "stop")

        metadata = store.get_metadata("abc123")
        assert metadata is not None
        assert metadata["last_operation"] == "stop"
        assert metadata["removed_at"] is None

    def test_removed_mapping_cleanup_requires_terminal_state(self, store):
        store.put("abc123", "my-app")

        assert store.cleanup_removed(max_age_hours=0) == 0
        assert store.get("abc123") == "my-app"

    def test_removed_mapping_cleanup_deletes_expired_rows(self, store):
        store.put("abc123", "my-app")
        store.touch("abc123", "rm")

        assert store.cleanup_removed(max_age_hours=0) == 1
        assert store.get("abc123") is None

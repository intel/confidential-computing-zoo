"""Unit tests for docktap/workload_store.py"""

import os
import tempfile

import pytest

from workload_store import WorkloadStore


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

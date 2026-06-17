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

"""
Lightweight SQLite-backed container → workload_id mapping store.

Persists on tmpfs (/dev/shm/docktap/) so mappings survive Docktap process
restarts but are cleared on host reboot (which also destroys all containers).
"""

import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from .config import WORKLOAD_DB

_DEFAULT_DB_PATH = WORKLOAD_DB

WORKLOAD_LABEL = "io.trucon.workload-id"
LAUNCH_LABEL = "io.trucon.launch-id"


class WorkloadStore:
    """Thread-safe container_id → workload_id persistence backed by SQLite."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create the database directory, file, and table if they do not exist.

        Safe to call on every startup — existing data is preserved.
        """
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, mode=0o700, exist_ok=True)

        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS container_workload (
                container_id TEXT PRIMARY KEY,
                workload_id  TEXT NOT NULL,
                created_at   TEXT NOT NULL
            )
            """
        )
        self._ensure_columns()
        self._conn.commit()

    def _ensure_columns(self) -> None:
        assert self._conn is not None, "call init_db() before schema migration"
        existing_columns = {
            row[1] for row in self._conn.execute("PRAGMA table_info(container_workload)")
        }
        if "last_seen_at" not in existing_columns:
            self._conn.execute(
                "ALTER TABLE container_workload ADD COLUMN last_seen_at TEXT"
            )
            self._conn.execute(
                "UPDATE container_workload SET last_seen_at = created_at WHERE last_seen_at IS NULL"
            )
        if "removed_at" not in existing_columns:
            self._conn.execute(
                "ALTER TABLE container_workload ADD COLUMN removed_at TEXT"
            )
        if "last_operation" not in existing_columns:
            self._conn.execute(
                "ALTER TABLE container_workload ADD COLUMN last_operation TEXT"
            )
            self._conn.execute(
                "UPDATE container_workload SET last_operation = 'create' WHERE last_operation IS NULL"
            )
        if "launch_id" not in existing_columns:
            self._conn.execute(
                "ALTER TABLE container_workload ADD COLUMN launch_id TEXT"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, container_id: str, workload_id: str, launch_id: Optional[str] = None, operation: str = "create") -> None:
        """Persist a container → workload mapping (upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        removed_at = now if operation == "rm" else None
        with self._lock:
            assert self._conn is not None, "call init_db() before put()"
            self._conn.execute(
                """
                INSERT INTO container_workload (
                    container_id,
                    workload_id,
                    created_at,
                    last_seen_at,
                    removed_at,
                    last_operation,
                    launch_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(container_id) DO UPDATE SET workload_id = excluded.workload_id,
                                                        last_seen_at = excluded.last_seen_at,
                                                        removed_at = CASE
                                                            WHEN excluded.last_operation = 'rm' THEN excluded.removed_at
                                                            ELSE NULL
                                                        END,
                                                        last_operation = excluded.last_operation,
                                                        launch_id = COALESCE(excluded.launch_id, container_workload.launch_id)
                """,
                (container_id, workload_id, now, now, removed_at, operation, launch_id),
            )
            self._conn.commit()

    def touch(self, container_id: str, operation: str) -> None:
        """Refresh lifecycle metadata for an existing mapping row."""
        now = datetime.now(timezone.utc).isoformat()
        removed_at = now if operation == "rm" else None
        with self._lock:
            assert self._conn is not None, "call init_db() before touch()"
            self._conn.execute(
                """
                UPDATE container_workload
                SET last_seen_at = ?,
                    removed_at = CASE WHEN ? = 'rm' THEN ? ELSE NULL END,
                    last_operation = ?
                WHERE container_id = ?
                """,
                (now, operation, removed_at, operation, container_id),
            )
            self._conn.commit()

    def get(self, container_id: str) -> Optional[str]:
        """Return the workload_id for *container_id*, or ``None`` if unknown."""
        with self._lock:
            assert self._conn is not None, "call init_db() before get()"
            row = self._conn.execute(
                "SELECT workload_id FROM container_workload WHERE container_id = ?",
                (container_id,),
            ).fetchone()
            return row[0] if row else None

    def get_metadata(self, container_id: str) -> Optional[Dict[str, Any]]:
        """Return full lifecycle metadata for a persisted mapping row."""
        with self._lock:
            assert self._conn is not None, "call init_db() before get_metadata()"
            row = self._conn.execute(
                """
                SELECT workload_id, created_at, last_seen_at, removed_at, last_operation, launch_id
                FROM container_workload WHERE container_id = ?
                """,
                (container_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "workload_id": row[0],
                "created_at": row[1],
                "last_seen_at": row[2],
                "removed_at": row[3],
                "last_operation": row[4],
                "launch_id": row[5],
            }

    def cleanup_removed(self, max_age_hours: float = 24) -> int:
        """Delete mappings whose terminal rm grace window has expired."""
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cutoff_str = cutoff.isoformat()
        with self._lock:
            assert self._conn is not None, "call init_db() before cleanup_removed()"
            cursor = self._conn.execute(
                """
                DELETE FROM container_workload
                WHERE removed_at IS NOT NULL AND removed_at < ?
                """,
                (cutoff_str,),
            )
            self._conn.commit()
            return cursor.rowcount

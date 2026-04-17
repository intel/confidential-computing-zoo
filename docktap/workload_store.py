"""
Lightweight SQLite-backed container → workload_id mapping store.

Persists on tmpfs (/dev/shm/docktap/) so mappings survive Docktap process
restarts but are cleared on host reboot (which also destroys all containers).
"""

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Optional

_DEFAULT_DB_PATH = os.environ.get(
    "DOCKTAP_WORKLOAD_DB", "/dev/shm/docktap/container_map.db"
)

WORKLOAD_LABEL = "io.trucon.workload-id"


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
        self._conn.commit()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def put(self, container_id: str, workload_id: str) -> None:
        """Persist a container → workload mapping (upsert)."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            assert self._conn is not None, "call init_db() before put()"
            self._conn.execute(
                """
                INSERT INTO container_workload (container_id, workload_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(container_id) DO UPDATE SET workload_id = excluded.workload_id,
                                                        created_at  = excluded.created_at
                """,
                (container_id, workload_id, now),
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

import sqlite3
import json
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple
import threading
import os
from datetime import datetime

# Import the DB path config
# Defaulting back to local if not defined
try:
    from config import COMMIT_QUEUE_DB
    DB_PATH = COMMIT_QUEUE_DB
except ImportError:
    DB_PATH = '/dev/shm/tc_api_queue/queue.db'

def ensure_db_dir(db_path: str):
    db_dir = os.path.dirname(db_path)
    if db_dir:
        try:
            os.makedirs(db_dir, exist_ok=True)
            # Apply strict 0700 DAC permissions to prevent intra-TD data leakage
            os.chmod(db_dir, 0o700)
        except Exception as e:
            print(f"Warning: Could not create or secure {db_dir} for sqlite DB. Using local fallback: {e}")

# Use thread-local storage if needed or rely on check_same_thread=False
# SQLite by default handles connections safely if isolation_level is set properly
# We want WAL mode for concurrent reads/writes and crash resilience

def init_db(db_path: str = DB_PATH):
    """Initialize the SQLite database with WAL and the CommitQueue table."""
    ensure_db_dir(db_path)
    with sqlite3.connect(db_path) as conn:
        # Enable Write-Ahead Logging for better concurrency and crash resilience
        conn.execute('PRAGMA journal_mode=WAL;')
        
        # Create standard CommitQueue table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS commit_queue (
                record_id TEXT PRIMARY KEY,
                event_id TEXT,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER DEFAULT 0,
                updated_at TEXT NOT NULL
            )
        ''')
        conn.commit()

@contextmanager
def get_db_connection(db_path: str = DB_PATH):
    """Context manager for database connections."""
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def insert_record(record_id: str, event_id: Optional[str], payload: Dict[str, Any], status: str, db_path: str = DB_PATH):
    """Insert a new record into the commit queue."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO commit_queue (record_id, event_id, payload, status, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (
            record_id, 
            event_id, 
            json.dumps(payload), 
            status, 
            datetime.utcnow().isoformat()
        ))
        conn.commit()

def update_status(record_id: str, status: str, db_path: str = DB_PATH):
    """Update the status of an existing record."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            UPDATE commit_queue
            SET status = ?, updated_at = ?
            WHERE record_id = ?
        ''', (status, datetime.utcnow().isoformat(), record_id))
        conn.commit()

def increment_retry(record_id: str, status: str, db_path: str = DB_PATH):
    """Increment the retry count and update status/timestamp."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            UPDATE commit_queue
            SET retry_count = retry_count + 1, status = ?, updated_at = ?
            WHERE record_id = ?
        ''', (status, datetime.utcnow().isoformat(), record_id))
        conn.commit()

def delete_record(record_id: str, db_path: str = DB_PATH):
    """Delete a record from the commit queue (e.g. after successful upload)."""
    with get_db_connection(db_path) as conn:
        conn.execute('DELETE FROM commit_queue WHERE record_id = ?', (record_id,))
        conn.commit()

def get_pending_records(db_path: str = DB_PATH) -> List[sqlite3.Row]:
    """Retrieve all pending records ordered by updated_at (oldest first)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue 
            WHERE status = 'PENDING'
            ORDER BY updated_at ASC
        ''')
        return cursor.fetchall()

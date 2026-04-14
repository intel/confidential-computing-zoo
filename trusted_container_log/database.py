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

def _migrate_legacy_schema(conn: sqlite3.Connection):
    """Detect legacy commit_queue schema and add missing columns."""
    cursor = conn.execute("PRAGMA table_info(commit_queue)")
    columns = {row[1] for row in cursor.fetchall()}
    
    if not columns:
        # Table doesn't exist yet, fresh install — nothing to migrate
        return
    
    new_columns = {
        'chain_id': "TEXT DEFAULT 'default'",
        'rtmr_extended': 'BOOLEAN DEFAULT NULL',
        'log_id': 'TEXT',
        'prev_log_id': 'TEXT',
        'mr_value': 'TEXT',
        'sequence_num': 'INTEGER DEFAULT 0',
        'confirmed_at': 'TEXT',
    }
    
    for col_name, col_def in new_columns.items():
        if col_name not in columns:
            conn.execute(f'ALTER TABLE commit_queue ADD COLUMN {col_name} {col_def}')
    
    conn.commit()

def init_db(db_path: str = DB_PATH):
    """Initialize the SQLite database with WAL and the CommitQueue table."""
    ensure_db_dir(db_path)
    with sqlite3.connect(db_path) as conn:
        # Enable Write-Ahead Logging for better concurrency and crash resilience
        conn.execute('PRAGMA journal_mode=WAL;')
        
        # Check if legacy schema exists (missing rtmr_extended column)
        _migrate_legacy_schema(conn)
        
        # Create CommitQueue table with expanded schema
        conn.execute('''
            CREATE TABLE IF NOT EXISTS commit_queue (
                record_id TEXT PRIMARY KEY,
                event_id TEXT,
                chain_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL,
                rtmr_extended BOOLEAN DEFAULT FALSE,
                log_id TEXT,
                prev_log_id TEXT,
                mr_value TEXT,
                sequence_num INTEGER NOT NULL,
                retry_count INTEGER DEFAULT 0,
                confirmed_at TEXT,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # Create chain_state table (one row per chain_id)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS chain_state (
                chain_id TEXT PRIMARY KEY,
                head_record_id TEXT,
                head_log_id TEXT,
                sequence_num INTEGER DEFAULT 0,
                mr_value TEXT,
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

def insert_record(record_id: str, event_id: Optional[str], payload: Dict[str, Any], status: str,
                   chain_id: str = 'default', rtmr_extended: bool = False,
                   prev_log_id: Optional[str] = None, mr_value: Optional[str] = None,
                   sequence_num: int = 0, db_path: str = DB_PATH):
    """Insert a new record into the commit queue."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO commit_queue (record_id, event_id, chain_id, payload, status,
                                      rtmr_extended, prev_log_id, mr_value, sequence_num, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            record_id, 
            event_id,
            chain_id,
            json.dumps(payload), 
            status,
            rtmr_extended,
            prev_log_id,
            mr_value,
            sequence_num,
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

def get_chain_state(chain_id: str, db_path: str = DB_PATH) -> Optional[sqlite3.Row]:
    """Get the current chain state for a given chain_id."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            'SELECT * FROM chain_state WHERE chain_id = ?', (chain_id,)
        )
        return cursor.fetchone()

def update_chain_state(chain_id: str, head_record_id: str, sequence_num: int,
                       mr_value: Optional[str] = None, head_log_id: Optional[str] = None,
                       db_path: str = DB_PATH):
    """Insert or update chain state for a given chain_id."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO chain_state (chain_id, head_record_id, head_log_id, sequence_num, mr_value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chain_id) DO UPDATE SET
                head_record_id = excluded.head_record_id,
                head_log_id = COALESCE(excluded.head_log_id, chain_state.head_log_id),
                sequence_num = excluded.sequence_num,
                mr_value = COALESCE(excluded.mr_value, chain_state.mr_value),
                updated_at = excluded.updated_at
        ''', (
            chain_id, head_record_id, head_log_id, sequence_num, mr_value,
            datetime.utcnow().isoformat()
        ))
        conn.commit()

def get_pending_by_chain(chain_id: str, db_path: str = DB_PATH) -> List[sqlite3.Row]:
    """Get pending records for a chain, ordered by sequence_num ascending."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue
            WHERE chain_id = ? AND status = 'PENDING' AND rtmr_extended = 1
            ORDER BY sequence_num ASC
        ''', (chain_id,))
        return cursor.fetchall()

def get_failed_by_chain(chain_id: str, db_path: str = DB_PATH) -> List[sqlite3.Row]:
    """Get failed records for a chain, ordered by sequence_num ascending."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue
            WHERE chain_id = ? AND status = 'FAILED'
            ORDER BY sequence_num ASC
        ''', (chain_id,))
        return cursor.fetchall()

def update_record_confirmed(record_id: str, log_id: str, db_path: str = DB_PATH):
    """Mark a record as confirmed with its Rekor log_id."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            UPDATE commit_queue
            SET status = 'CONFIRMED', log_id = ?, confirmed_at = ?, updated_at = ?
            WHERE record_id = ?
        ''', (log_id, datetime.utcnow().isoformat(), datetime.utcnow().isoformat(), record_id))
        conn.commit()

def delete_non_extended_records(db_path: str = DB_PATH) -> int:
    """Delete records where rtmr_extended is FALSE or NULL. Returns count deleted."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            DELETE FROM commit_queue WHERE rtmr_extended IS NULL OR rtmr_extended = 0
        ''')
        conn.commit()
        return cursor.rowcount

def get_highest_extended_record(chain_id: str, db_path: str = DB_PATH) -> Optional[sqlite3.Row]:
    """Get the record with the highest sequence_num that has rtmr_extended=TRUE."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue
            WHERE chain_id = ? AND rtmr_extended = 1
            ORDER BY sequence_num DESC
            LIMIT 1
        ''', (chain_id,))
        return cursor.fetchone()

def get_all_chain_ids(db_path: str = DB_PATH) -> List[str]:
    """Get all distinct chain_ids from the commit_queue."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('SELECT DISTINCT chain_id FROM commit_queue')
        return [row[0] for row in cursor.fetchall()]

def get_queue_stats(db_path: str = DB_PATH) -> Dict[str, Any]:
    """Get queue statistics: queued_count, failed_count, next_sequence_num."""
    with get_db_connection(db_path) as conn:
        queued = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'PENDING'"
        ).fetchone()[0]
        failed = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'FAILED'"
        ).fetchone()[0]
        next_seq = conn.execute(
            "SELECT MIN(sequence_num) FROM commit_queue WHERE status = 'PENDING' AND rtmr_extended = 1"
        ).fetchone()[0]
        return {
            'queued_count': queued,
            'failed_count': failed,
            'next_sequence_num': next_seq,
        }

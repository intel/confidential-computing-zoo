import sqlite3
import json
from contextlib import contextmanager
from typing import Optional, List, Dict, Any, Tuple
import threading
import os
from datetime import datetime

# Module-level default DB path.  Overridden at import time by trucon/app.py
# or via the COMMIT_QUEUE_DB environment variable.
DB_PATH = os.environ.get('COMMIT_QUEUE_DB', '/dev/shm/tc_api_queue/queue.db')

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
        'event_digest': 'TEXT',
        'idempotency_key': 'TEXT',
    }
    
    for col_name, col_def in new_columns.items():
        if col_name not in columns:
            conn.execute(f'ALTER TABLE commit_queue ADD COLUMN {col_name} {col_def}')
    
    # Ensure unique index on idempotency_key (ALTER TABLE can't add UNIQUE columns)
    try:
        conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_idempotency_key ON commit_queue(idempotency_key)')
    except sqlite3.OperationalError:
        pass  # Index already exists

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
                event_digest TEXT,
                idempotency_key TEXT UNIQUE,
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
                   sequence_num: int = 0, event_digest: Optional[str] = None,
                   idempotency_key: Optional[str] = None,
                   db_path: str = DB_PATH):
    """Insert a new record into the commit queue."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            INSERT INTO commit_queue (record_id, event_id, chain_id, payload, status,
                                      rtmr_extended, prev_log_id, mr_value, sequence_num,
                                      event_digest, idempotency_key, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            event_digest,
            idempotency_key,
            datetime.utcnow().isoformat()
        ))
        conn.commit()

def get_record_by_idempotency_key(idempotency_key: str, chain_id: str, db_path: str = DB_PATH) -> Optional[sqlite3.Row]:
    """Look up an existing record by idempotency_key and chain_id. Returns None if not found."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute(
            'SELECT * FROM commit_queue WHERE idempotency_key = ? AND chain_id = ?',
            (idempotency_key, chain_id)
        )
        return cursor.fetchone()


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
    """Get failed records (retryable + terminal) for a chain, ordered by sequence_num ascending."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue
            WHERE chain_id = ? AND status IN ('FAILED_RETRYABLE', 'FAILED_TERMINAL')
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
    """Get queue statistics with granular state counts."""
    with get_db_connection(db_path) as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'PENDING'"
        ).fetchone()[0]
        submitting = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'SUBMITTING'"
        ).fetchone()[0]
        failed_retryable = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'FAILED_RETRYABLE'"
        ).fetchone()[0]
        failed_terminal = conn.execute(
            "SELECT COUNT(*) FROM commit_queue WHERE status = 'FAILED_TERMINAL'"
        ).fetchone()[0]
        next_row = conn.execute(
            "SELECT sequence_num, record_id FROM commit_queue WHERE status = 'PENDING' AND rtmr_extended = 1 ORDER BY sequence_num ASC LIMIT 1"
        ).fetchone()
        next_seq = next_row[0] if next_row else None
        next_record_id = next_row[1] if next_row else None
        return {
            'queued_count': pending,
            'submitting_count': submitting,
            'failed_retryable_count': failed_retryable,
            'failed_terminal_count': failed_terminal,
            'next_sequence_num': next_seq,
            'next_record_id': next_record_id,
        }

def get_latest_state(chain_id: str = 'default', db_path: str = DB_PATH) -> Dict[str, Any]:
    """Get LatestState for a chain: confirmed head + pending summary."""
    with get_db_connection(db_path) as conn:
        state = conn.execute(
            'SELECT head_log_id, mr_value FROM chain_state WHERE chain_id = ?',
            (chain_id,)
        ).fetchone()
        latest_confirmed_log_id = state[0] if state else None
        latest_mr_value = state[1] if state else None

        pending_rows = conn.execute(
            "SELECT event_id FROM commit_queue WHERE chain_id = ? AND status = 'PENDING' ORDER BY sequence_num ASC",
            (chain_id,)
        ).fetchall()
        pending_event_ids = [row[0] for row in pending_rows if row[0] is not None]

        return {
            'latest_confirmed_log_id': latest_confirmed_log_id,
            'pending_record_count': len(pending_rows),
            'pending_event_ids': pending_event_ids,
            'latest_mr_value': latest_mr_value,
        }

def reset_submitting_to_pending(db_path: str = DB_PATH) -> int:
    """Reset any SUBMITTING records to PENDING (crash recovery)."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            UPDATE commit_queue
            SET status = 'PENDING', updated_at = ?
            WHERE status = 'SUBMITTING'
        ''', (datetime.utcnow().isoformat(),))
        conn.commit()
        return cursor.rowcount

def set_status_submitting(record_id: str, db_path: str = DB_PATH):
    """Mark a record as SUBMITTING before backend call."""
    with get_db_connection(db_path) as conn:
        conn.execute('''
            UPDATE commit_queue
            SET status = 'SUBMITTING', updated_at = ?
            WHERE record_id = ?
        ''', (datetime.utcnow().isoformat(), record_id))
        conn.commit()

def get_chain_records(chain_id: str, db_path: str = DB_PATH) -> List[sqlite3.Row]:
    """Get all records for a chain, ordered by sequence_num ascending."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute('''
            SELECT * FROM commit_queue
            WHERE chain_id = ?
            ORDER BY sequence_num ASC
        ''', (chain_id,))
        return cursor.fetchall()

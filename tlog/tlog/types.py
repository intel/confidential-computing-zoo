from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

class SubmitStatus(str, Enum):
    OPEN = "open"
    PENDING = "pending"
    SUBMITTING = "submitting"
    CONFIRMED = "confirmed"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_TERMINAL = "failed_terminal"

@dataclass(slots=True)
class Entry:
    key: str
    value: Any

@dataclass(slots=True)
class Record:
    entries: List[Entry] = field(default_factory=list)

@dataclass(slots=True)
class EventLog:
    event_id: str
    event_type: str
    digest: str
    record: Record
    created: datetime
    mr: Optional[str] = None
    global_id: Optional[str] = None
    signature: Optional[str] = None
    pub_key: Optional[str] = None

@dataclass(slots=True)
class RecordContext:
    record_id: str
    chain_ref: Optional[str]
    created_at: datetime
    prev_log_id: Optional[str] = None

@dataclass(slots=True)
class CommitResult:
    record_id: str
    event_id: Optional[str]
    queue_status: SubmitStatus
    mr_value: Optional[str] = None
    prev_mr_value: Optional[str] = None
    pending_reason: Optional[str] = None

@dataclass(slots=True)
class CommitQueueStatus:
    has_queued_records: bool
    queued_record_count: int
    next_record_id: Optional[str] = None
    total_retry_count: int = 0

@dataclass(slots=True)
class LatestState:
    latest_confirmed_log_id: Optional[str]
    pending_record_count: int
    pending_event_ids: List[str] = field(default_factory=list)
    latest_mr_value: Optional[str] = None

@dataclass(slots=True)
class VerificationResult:
    success: bool
    errors: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)

# Trusted Log Python Module API Definition

## Scope

This document defines the Python module API for Trusted Log.
It specifies classes, dataclasses, Protocol interfaces, and method signatures for in-process usage by trust-bootstrap workflows.

## Module Layout

Recommended Python module boundaries:

- `trusted_log.api`: high-level orchestration API exposed to callers.
- `trusted_log.types`: dataclasses, enums, and typed aliases.
- `trusted_log.adapters.local_mr`: local measurement adapter Protocol and implementations.
- `trusted_log.adapters.immutable_log`: immutable backend adapter Protocol and implementations.
- `trusted_log.errors`: structured exception hierarchy.

## Core Types

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional


class SubmitStatus(str, Enum):
	CONFIRMED = "confirmed"
	PENDING = "pending"
	FAILED = "failed"


@dataclass(slots=True)
class Entry:
	key: str
	value: str


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
class SubmitResult:
	record_id: str
	event_id: Optional[str]
	status: SubmitStatus
	mr_value: Optional[str] = None
	prev_mr_value: Optional[str] = None
	pending_reason: Optional[str] = None
	backend: Optional[str] = None
	confirmed_at: Optional[datetime] = None


@dataclass(slots=True)
class CommitQueueStatus:
	has_queued_records: bool
	queued_record_count: int
	next_record_id: Optional[str] = None


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
```

## Adapter Protocols

```python
from typing import Any, Dict, List, Literal, Optional, Protocol


class LocalMRAdapter(Protocol):
	def extend(self, record_id: str, event_digest: str) -> tuple[Optional[str], Optional[str]]:
		"""Return (mr_value, prev_mr_value)."""

	def query(self, index: Optional[int] = None) -> tuple[Optional[str], str]:
		"""Return (mr_value, timestamp_iso)."""


class ImmutableLogAdapter(Protocol):
	def submit(self, event_log: EventLog, prev_log_id: Optional[str] = None) -> tuple[Optional[str], Literal["confirmed", "pending"], Dict[str, Any]]:
		"""Return (log_id, status, backend_receipt)."""

	def get(self, log_id: str) -> tuple[EventLog, Dict[str, Any]]:
		"""Return (event_log, metadata)."""

	def traverse(self, start_log_id: str, direction: Literal["backward", "forward"], max_hops: Optional[int] = None) -> List[EventLog]:
		"""Return ordered records from chain traversal."""
```

## Trusted Log API Class

```python
from typing import Any, Dict, Optional


class TrustedLogAPI:
	def __init__(self, local_mr: LocalMRAdapter, immutable_log: ImmutableLogAdapter) -> None:
		...

	def init_record(self, prev_log_id: Optional[str] = None, context: Optional[Dict[str, Any]] = None) -> RecordContext:
		...

	def add_entry(self, record_id: str, entry: Entry) -> int:
		"""Return total number of entries attached to record_id."""

	def commit_record(
		self,
		record_id: str,
		event_type: str,
		event_id: Optional[str] = None,
		commit_options: Optional[Dict[str, Any]] = None,
	) -> CommitResult:
		"""Finalize the in-progress record and enqueue it for publication."""

	def submit_record(self, record_id: str, submit_options: Optional[Dict[str, Any]] = None) -> SubmitResult:
		"""Submit a previously committed queued record and apply queue state transitions internally."""

	def get_commit_queue_status(self, scope: Optional[str] = None) -> CommitQueueStatus:
		"""Return whether committed queued work exists and which record should be attempted next."""

	def get_latest_state(self, scope: Optional[str] = None) -> LatestState:
		"""Return a compact summary of confirmed state, pending-record count, and pending event IDs."""

	def get_event_log(self, log_uuid: str) -> EventLog:
		"""Return the committed EventLog resolved by immutable log UUID/log ID."""

	def verify_record(self, target: str, policy: Optional[Dict[str, Any]] = None) -> VerificationResult:
		"""Verify a target record or chain by replaying persisted immutable event-log content."""
		...
```

## TrustedLogAPI Behavioral Requirements

- `commit_record()` finalizes an in-progress record, computes its canonical digest, and enqueues it for later publication.
- `submit_record(record_id)` publishes a previously committed queued record and must apply queue-state transitions internally.
- `get_commit_queue_status()` is the worker-facing queue-drain helper and should not be treated as a full queue inspection API.
- `get_latest_state()` is a compact summary API and may expose pending event identifiers, but not full retry metadata.
- `get_event_log(log_uuid)` resolves a committed immutable event by backend log identifier so callers can replay or inspect the exact persisted payload.
- `verify_record()` should verify records by replaying canonical event-log content rather than trusting stored digest metadata alone.
- Implementations of `TrustedLogAPI` must be safe for multi-threaded or multi-worker use where `commit_record()` and `submit_record()` may run concurrently against shared chain state.

## Error Model

```python
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass(slots=True)
class TrustedLogError(Exception):
	code: str
	message: str
	stage: str
	retryable: bool
	details: Optional[Dict[str, Any]] = None


class RecordNotFoundError(TrustedLogError):
	pass


class BackendSubmitError(TrustedLogError):
	pass


class VerificationError(TrustedLogError):
	pass
```

Stage values should remain stable:

- `init`
- `add_entry`
- `commit`
- `queue`
- `submit`
- `extend`
- `verify`

## Lifecycle (Python Caller)

```python
ctx = trusted_log.init_record(prev_log_id=last_log_id)
trusted_log.add_entry(ctx.record_id, Entry(key="docker-pull", value=image_ref))
trusted_log.add_entry(ctx.record_id, Entry(key="verify-sbom", value=sbom_digest))
commit = trusted_log.commit_record(ctx.record_id, event_type="launch-container")
queue = trusted_log.get_commit_queue_status()

if queue.has_queued_records and queue.next_record_id is not None:
	result = trusted_log.submit_record(queue.next_record_id)
else:
	result = SubmitResult(record_id=ctx.record_id, event_id=commit.event_id, status=SubmitStatus.PENDING)

state = trusted_log.get_latest_state()
event_log = trusted_log.get_event_log(log_uuid="log-uuid-example")

verify = trusted_log.verify_record(target=result.event_id or commit.event_id or ctx.record_id)
```

## Compatibility Rules

- Callers depend on `TrustedLogAPI` and Protocols, not concrete backend classes.
- New backends must satisfy the same adapter Protocols.
- `get_latest_state()` should remain a compact summary API; it may expose pending event IDs, but queue-draining logic should use `get_commit_queue_status()` plus `submit_record(record_id)`.
- `get_event_log(log_uuid)` should resolve the immutable backend identifier exposed by the committed log, whether the backend calls it `log_id`, `uuid`, or `global_id`.
- `verify_record()` should support replay-based verification of committed immutable event logs, including digest recomputation and chain-link validation.
- Queue state transitions after publication should be performed inside `submit_record()` rather than by callers.
- `TrustedLogAPI` implementations should provide concurrency-safe behavior across commit and submit operations running in different worker contexts.
- Type and field names in this document are treated as contract-level API.

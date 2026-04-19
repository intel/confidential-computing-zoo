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
	value: Any  # JSON-compatible: str, int, float, bool, None, list, dict


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
	chain_id: str
	sequence_num: int
	event_id: Optional[str]
	queue_status: SubmitStatus
	mr_value: Optional[str] = None
	prev_mr_value: Optional[str] = None
	pending_reason: Optional[str] = None


@dataclass(slots=True)
class CommitQueueStatus:
	total_pending: int
	total_confirmed: int
	total_failed: int
	chains: Dict[str, Any] = field(default_factory=dict)


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
	def extend(self, index: int, digest: str) -> tuple[Optional[str], Optional[str]]:
		"""Extend the measurement register at `index` with `digest`. Return (mr_value, prev_mr_value)."""

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

`TrustedLogAPI` is the **tc_api-side** client. It performs DSSE signing locally using the caller's OIDC identity token and delegates sequencing (RTMR extend + queue INSERT + chain state) to the TruCon via REST.

```python
from typing import Any, Dict, Optional


class TrustedLogAPI:
	def __init__(self, local_mr: LocalMRAdapter = None, immutable_log: ImmutableLogAdapter = None,
	             trucon_url: str = "http://127.0.0.1:8001") -> None:
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
		"""Sign the DSSE envelope locally and POST the bundle to TruCon for sequencing."""

	def get_commit_queue_status(self, scope: Optional[str] = None) -> CommitQueueStatus:
		"""Query the TruCon GET /status endpoint for queue statistics."""

	def get_event_log(self, log_uuid: str) -> EventLog:
		"""Return the committed EventLog resolved by immutable log UUID/log ID."""

	def verify_record(self, target: str, policy: Optional[Dict[str, Any]] = None) -> VerificationResult:
		"""Verify a target immutable-log chain tail using policy such as chain_id and signer identity."""
		...
```

Note: `submit_record()` and `get_latest_state()` are no longer exposed on the tc_api side. Submission is handled by the embedded daemon inside the TruCon. Queue status is available via `get_commit_queue_status()` which queries the TruCon's `GET /status` endpoint.

## TrustedLogAPI Behavioral Requirements

- `commit_record()` signs a DSSE envelope locally (without `prev_log_id` in the predicate), then POSTs the signed bundle to the TruCon sequencer. The TruCon serializes RTMR extend + SQLite INSERT + chain state update under a `threading.Lock()`.
- Submission to Rekor is handled by the embedded daemon inside the TruCon. Callers do not invoke submission manually.
- `get_commit_queue_status()` queries the TruCon `GET /status` endpoint for aggregate queue statistics (total pending, confirmed, failed counts per chain).
- `get_event_log(log_uuid)` resolves a committed immutable event by backend log identifier so callers can replay or inspect the exact persisted payload.
- `verify_record()` verifies immutable-backend entries starting from a confirmed tail log identifier. Callers can provide policy such as `chain_id` and `signer_identity`, and the result includes structured per-entry detail for operator tooling.
- `TrustedLogAPI` (tc_api-side) is stateless and safe for multi-worker deployment. All ordering and state are managed by the single-instance TruCon.

For operator-facing workflows, prefer the package CLI:

```bash
tc-verify --evidence evidence.json
```

In the preferred flow, the CLI derives `chain_id` and `head_log_id` from an exported attested-head evidence package, performs immutable-backend replay from that attested tail, and validates that replay reaches the exported head. The legacy `tc-verify <chain_id>` form remains available only as a transitional live TruCon fallback.

For producer-side attested evidence export, TruCon also exposes:

```bash
GET /evidence/<chain_id>
```

This endpoint returns a v1 attested-head evidence package for the chain's latest confirmed public head only. It is a strict read-only surface: if the chain has no confirmed `head_log_id`, if quote acquisition fails, or if the quote-backed report-data value does not match the producer-computed binding target, the request fails rather than returning degraded evidence.

For the longer-term operator-facing verification model and evidence-package boundary, see [verification.md](verification.md).

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

## TruCon REST Contract

The TruCon is a single-instance FastAPI service (started with `--workers 1`) that owns sequencing, the SQLite queue, and the embedded submit daemon.

| Endpoint | Method | Description |
|---|---|---|
| `/commit` | POST | Accept a signed DSSE bundle. Serialize RTMR extend + INSERT + chain state under lock. Return `{record_id, chain_id, sequence_num, mr_value, status}`. |
| `/chain-state/{chain_id}` | GET | Return current chain state: `{chain_id, head_record_id, head_log_id, sequence_num, mr_value}`. |
| `/evidence/{chain_id}` | GET | Return a v1 attested-head evidence package for the chain's latest confirmed public head. Fails if no confirmed immutable-log head exists or if quote acquisition / binding validation fails. |
| `/verify-chain/{chain_id}` | GET | Return local chain verification details: sequence continuity, RTMR checks, Rekor confirmation state, and non-TEE `prev_log_id` fallback diagnostics. |
| `/status` | GET | Return aggregate queue statistics: total pending, confirmed, and failed counts per chain. |

See `src/tc_api/trucon/app.py` for Pydantic request/response models (`CommitRequest`, `CommitResponse`, `ChainStateResponse`, `CommitQueueStatusResponse`, `ChainVerificationResponse`).

## Lifecycle (Python Caller)

```python
# tc_api side — stateless, multi-worker safe
ctx = trusted_log.init_record()
trusted_log.add_entry(ctx.record_id, Entry(key="docker-pull", value=image_ref))
trusted_log.add_entry(ctx.record_id, Entry(key="verify-sbom", value={"digest": sbom_digest, "format": "spdx"}))

# Signs DSSE locally, POSTs to TruCon which sequences (RTMR extend + queue INSERT)
commit = trusted_log.commit_record(ctx.record_id, event_type="launch-container")
# commit.queue_status == SubmitStatus.PENDING
# commit.mr_value contains the extended RTMR value

# Submission to Rekor happens automatically via the embedded daemon.
# No manual submit_record() call needed.

# Check queue status (queries TruCon GET /status)
queue = trusted_log.get_commit_queue_status()

# Retrieve a confirmed event log by its Rekor log ID
event_log = trusted_log.get_event_log(log_uuid="log-uuid-example")

# Resolve the confirmed chain tail from TruCon, then verify immutable-backend entries
verify = trusted_log.verify_record(target="head_log_id_value", policy={"chain_id": "default"})
```

## Compatibility Rules

- Callers depend on `TrustedLogAPI` and Protocols, not concrete backend classes.
- New backends must satisfy the same adapter Protocols.
- `get_event_log(log_uuid)` should resolve the immutable backend identifier exposed by the committed log, whether the backend calls it `log_id`, `uuid`, or `global_id`.
- `verify_record()` should support replay-based verification of committed immutable event logs, including structured per-entry detail, digest recomputation, and chain-link validation within the immutable backend's scope.
- Queue state transitions (pending → confirmed / failed) are managed internally by the embedded submit daemon in the TruCon. Callers never drive submission.
- `TrustedLogAPI` (tc_api-side) is stateless. All sequencing state lives in the TruCon's SQLite database and in-memory chain state.
- The TruCon must run as a single instance (`--workers 1`) to guarantee lock-based serialization.
- Type and field names in this document are treated as contract-level API.

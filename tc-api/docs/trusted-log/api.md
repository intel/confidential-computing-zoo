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
	idempotency_key: Optional[str] = None


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
	def submit(self, event_log: EventLog) -> tuple[Optional[str], Literal["confirmed", "pending"], Dict[str, Any]]:
		"""Return (log_id, status, backend_receipt). Backend linkage metadata is not protocol truth."""

	def get(self, log_id: str) -> tuple[EventLog, Dict[str, Any]]:
		"""Return (event_log, metadata)."""

	def traverse(self, start_log_id: str, direction: Literal["backward", "forward"], max_hops: Optional[int] = None) -> List[EventLog]:
		"""Return ordered records from chain traversal."""

	def find_entries_by_payload_hash(self, payload_hash: str) -> List[Any]:
		"""Return predecessor candidates discovered by immutable-backend payload hash lookup."""
```

## Trusted Log API Class

`TrustedLogAPI` is the **tc_api-side** client. It reserves predecessor contracts, performs DSSE signing locally using the caller's OIDC identity token, and delegates sequencing (validation + RTMR extend + queue INSERT + chain state) to the TruCon via REST.

```python
from typing import Any, Dict, Optional


class TrustedLogAPI:
	def __init__(self, local_mr: LocalMRAdapter = None, immutable_log: ImmutableLogAdapter = None,
	             trucon_url: str = "http://127.0.0.1:8001") -> None:
		...

	def init_record(self, context: Optional[Dict[str, Any]] = None) -> RecordContext:
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
		"""Reserve predecessor state, sign the DSSE envelope locally, and POST the signed bundle plus intent token to TruCon for sequencing."""

	def get_commit_queue_status(self, scope: Optional[str] = None) -> CommitQueueStatus:
		"""Query the TruCon GET /status endpoint for queue statistics."""

	def get_event_log(self, log_uuid: str) -> EventLog:
		"""Return the committed EventLog resolved by immutable log UUID/log ID."""

	def verify_record(self, target: str, policy: Optional[Dict[str, Any]] = None) -> VerificationResult:
		"""Verify a target immutable-log chain tail using policy such as chain_id and signer identity, returning structured predecessor diagnostics."""
		...
```

Note: `submit_record()` and `get_latest_state()` are no longer exposed on the tc_api side. Submission is handled by the embedded daemon inside the TruCon. Queue status is available via `get_commit_queue_status()` which queries the TruCon's `GET /status` endpoint.

## TrustedLogAPI Behavioral Requirements

- `commit_record()` now follows `reserve -> sign -> commit(intent_token)`: it first reserves a durable predecessor contract from TruCon, signs a DSSE envelope containing `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, then POSTs the signed bundle plus `intent_token` to the TruCon sequencer. The TruCon serializes validation, RTMR extend, SQLite INSERT, and chain state update under a `threading.Lock()`.
- Submission to Rekor is handled by the embedded daemon inside the TruCon. Callers do not invoke submission manually.
- `get_commit_queue_status()` queries the TruCon `GET /status` endpoint for aggregate queue statistics (total pending, confirmed, failed counts per chain).
- `get_event_log(log_uuid)` resolves a committed immutable event by backend log identifier so callers can replay or inspect the exact persisted payload.
- `verify_record()` verifies immutable-backend entries starting from a confirmed tail log identifier. Callers can provide policy such as `chain_id` and `signer_identity`, and the result includes structured per-entry detail for operator tooling.
- `TrustedLogAPI` (tc_api-side) is stateless and safe for multi-worker deployment. All ordering and state are managed by the single-instance TruCon.

### tc_api Chain Routing Contract

The current tc_api integration uses explicit `chain_ref` routing when it calls `init_record()`:

- build and publish create records on `TRANSPARENCY_SERVICE_CHAIN_ID`, which defaults to `tc-api-service`;
- launch creates records on `TRANSPARENCY_WORKLOAD_CHAIN_PREFIX + workload_id`, which defaults to `tc-api-workload-<workload_id>`.

This is now the intended caller contract for tc_api-facing transparency operations. Using the legacy `default` chain for new build/publish receipts is no longer the operationally preferred path.

### Chain Owner Key Persistence Contract

The owner key used for reservation-backed commit authorization is chain-scoped and persistent.

- Event Log 0 stores the owner public key in the baseline payload as `pub_key`.
- later commits for the same chain must sign matching `owner_authorization` payloads with the corresponding private key.
- tc_api therefore persists the chain owner private key under `OWNER_KEY_DIR` and reuses it across process restarts.

If the persisted key is lost while the TruCon chain history remains, `/commit` will reject future writes for that chain because the live authorization signer no longer matches the baseline `pub_key`. Operators should therefore treat owner-key persistence and chain history as one recovery domain.

For the current real-Rekor smoke path, two implementation limitations remain important for operators and tests:

- replay treats Rekor `payloadHash(sha256)` lookup as predecessor candidate discovery only, not protocol truth
- opt-in real-Rekor coverage now distinguishes public replay proof from cache-assisted fallback; same-process cache may still help local retrieval, but it no longer counts as publicly auditable replay truth

For the current mirror-backed replay path, one more implementation detail matters:

- when public Rekor readback is hash-only, the Sigstore adapter can re-materialize DSSE payload fields from `OciBundleMirror`, keyed by `payload_hash`;
- the mirror is non-authoritative and may be local OCI-layout-style storage or a live registry-backed repository;
- this enables `tc-verify --mirror-dir ... --require-mirror` to distinguish `public-only` replay from `public+mirrored` replay.

For operator-facing workflows, prefer the package CLI:

```bash
tc-verify --evidence evidence.json
```

In the current CLI contract, the CLI derives `chain_id` and `head_log_id` from an exported attested-head evidence package, performs immutable-backend replay from that attested tail, and validates that replay reaches the exported head. Bare `tc-verify <chain_id>` is no longer a supported external verification path; live TruCon-backed verification requires an explicit troubleshooting selector and is labeled as internal diagnostics rather than as the operator verifier contract.

The CLI also reports the provenance boundary explicitly:

- public replay covers history, predecessor continuity, and Event Log 0 baseline origin;
- mirrored replay covers the same history while obtaining DSSE payload material from `OciBundleMirror` rather than from public Rekor entry bodies alone;
- exported evidence covers current-head quote binding only;
- cache-assisted replay is surfaced as degraded or unsupported rather than silently reported as public proof.

The operator-facing CLI result now also includes a top-level `diagnostics` object containing replay reachability and provenance, fallback validity, the first top-level error string, and the first replay entry with a boundary, predecessor, or materialization problem.

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
| `/commit-intents/reserve` | POST | Allocate a durable commit intent with `sequence_num`, `prev_event_digest`, `prev_lookup_hash`, and `intent_token`. Returns an existing intent or committed result for the same idempotency key. |
| `/commit` | POST | Accept a signed DSSE bundle and optional `intent_token`. Validate the signed bundle against the reserved contract, then serialize RTMR extend + INSERT + chain state under lock. Return `{record_id, chain_id, sequence_num, mr_value, status}`. |
| `/init-chain/{chain_id}/baseline` | GET | Return Event Log 0 baseline inputs (`rtmr_value`, `ccel_digest`, `init_token`) before signing. |
| `/init-chain` | POST | Consume a reserved baseline intent plus `init_token` and insert Event Log 0 as `sequence_num=1`. |
| `/chain-state/{chain_id}` | GET | Return current chain state: `{chain_id, head_record_id, head_log_id, sequence_num, mr_value}`. |
| `/evidence/{chain_id}` | GET | Return a v1 attested-head evidence package for the chain's latest confirmed public head. Fails if no confirmed immutable-log head exists or if quote acquisition / binding validation fails. |
| `/verify-chain/{chain_id}` | GET | Return local chain verification details: sequence continuity, RTMR checks, Rekor confirmation state, and signed predecessor diagnostics exposed as `predecessor_ok`, `predecessor_status`, `prev_event_digest`, `prev_lookup_hash`, `candidate_count`, and related pipeline counts. |
| `/status` | GET | Return aggregate queue statistics: total pending, confirmed, and failed counts per chain. |

See `tc_api/trucon/schemas.py` for Pydantic request/response models (`CommitRequest`, `CommitResponse`, `ChainStateResponse`, `CommitQueueStatusResponse`, `ChainVerificationResponse`). `tc_api/trucon/app.py` imports those schemas and binds them to FastAPI routes.

## Lifecycle (Python Caller)

```python
# tc_api side — stateless, multi-worker safe
ctx = trusted_log.init_record(context={"chain_ref": "tc-api-service"})
trusted_log.add_entry(ctx.record_id, Entry(key="docker-pull", value=image_ref))
trusted_log.add_entry(ctx.record_id, Entry(key="verify-sbom", value={"digest": sbom_digest, "format": "spdx"}))

# Reserves predecessor contract, signs DSSE locally, POSTs to TruCon which validates and sequences (RTMR extend + queue INSERT)
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
verify = trusted_log.verify_record(target="head_log_id_value", policy={"chain_id": "tc-api-service"})
```

The preferred operator-facing surface remains `tc-verify --evidence ...`; direct `verify_record()` usage is best understood as the library-level replay primitive beneath that CLI flow.

## Compatibility Rules

- Callers depend on `TrustedLogAPI` and Protocols, not concrete backend classes.
- New backends must satisfy the same adapter Protocols.
- `get_event_log(log_uuid)` should resolve the immutable backend identifier exposed by the committed log, whether the backend calls it `log_id`, `uuid`, or `global_id`.
- `verify_record()` should support replay-based verification of committed immutable event logs, including structured per-entry detail, digest recomputation, signed predecessor validation using `sequence_num`, `prev_event_digest`, and `prev_lookup_hash`, and machine-readable predecessor verdicts such as `origin`, `proven`, `missing`, `ambiguous`, `unverifiable`, `lookup_failed`, and `decode_failed`.
- Queue state transitions (pending → confirmed / failed) are managed internally by the embedded submit daemon in the TruCon. Callers never drive submission.
- `TrustedLogAPI` (tc_api-side) is stateless. All sequencing state lives in the TruCon's SQLite database and in-memory chain state.
- The TruCon must run as a single instance (`--workers 1`) to guarantee lock-based serialization.
- Type and field names in this document are treated as contract-level API.

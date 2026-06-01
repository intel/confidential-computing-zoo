# tlog API Surface

This document describes the Python-level surface provided by the `tlog` package itself.

It does not describe higher-level clients, service endpoints, or workflow orchestration built on top of `tlog`.

## Re-Exports

The package root re-exports the main public types and helpers:

```python
from tlog import (
    Entry,
    Record,
    EventLog,
    RecordContext,
    CommitResult,
    CommitQueueStatus,
    LatestState,
    VerificationResult,
    SubmitStatus,
    TrustedLogError,
    RecordNotFoundError,
    BackendSubmitError,
    VerificationError,
    ImmutableLogAdapter,
    LocalMRAdapter,
    canonical_json,
    compute_entry_digest,
    compute_event_digest,
)
```

## Data Types

### `SubmitStatus`

Current enum members:

- `open`
- `pending`
- `submitting`
- `confirmed`
- `failed_retryable`
- `failed_terminal`

The enum is shared package vocabulary. An integrating application may use only a subset of these states.

### `Entry`

```python
Entry(key: str, value: Any)
```

Represents one logical field in a record. `value` may be any JSON-compatible payload that the caller can serialize deterministically.

### `Record`

```python
Record(entries: list[Entry] = [])
```

An ordered collection of entries.

### `EventLog`

```python
EventLog(
    event_id: str,
    event_type: str,
    digest: str,
    record: Record,
    created: datetime,
    mr: str | None = None,
    global_id: str | None = None,
    signature: str | None = None,
    pub_key: str | None = None,
)
```

Represents a logical event plus optional signature and measurement metadata.

The package does not require any specific interpretation of `mr`, `global_id`, `signature`, or `pub_key`; those fields are integration-defined.

### `RecordContext`

```python
RecordContext(
    record_id: str,
    chain_ref: str | None,
    created_at: datetime,
    prev_log_id: str | None = None,
)
```

Caller-side assembly context for one in-progress record.

### `CommitResult`

```python
CommitResult(
    record_id: str,
    event_id: str | None,
    queue_status: SubmitStatus,
    mr_value: str | None = None,
    prev_mr_value: str | None = None,
    pending_reason: str | None = None,
)
```

Generic result model that higher-level integrations can reuse when exposing commit outcomes.

### `CommitQueueStatus`

```python
CommitQueueStatus(
    has_queued_records: bool,
    queued_record_count: int,
    next_record_id: str | None = None,
    total_retry_count: int = 0,
)
```

Package-level queue status vocabulary. `tlog` does not implement the queue itself.

### `LatestState`

```python
LatestState(
    latest_confirmed_log_id: str | None,
    pending_record_count: int,
    pending_event_ids: list[str] = [],
    latest_mr_value: str | None = None,
)
```

Shared shape for reporting the latest known state of a chain-like integration.

### `VerificationResult`

```python
VerificationResult(
    success: bool,
    errors: list[str] = [],
    details: dict[str, Any] = {},
)
```

Minimal verification outcome container.

## Error Types

### `TrustedLogError`

```python
TrustedLogError(
    code: str,
    message: str,
    stage: str,
    retryable: bool,
    details: dict[str, Any] | None = None,
)
```

Base structured exception for trusted-log operations.

Derived errors:

- `RecordNotFoundError`
- `BackendSubmitError`
- `VerificationError`

## Digest Helpers

### `canonical_json(data)`

Returns a deterministic JSON string using:

- sorted object keys
- compact separators
- UTF-8 content without forced ASCII escaping

### `compute_entry_digest(key, value)`

Computes:

```text
sha384(canonical_json({"key": key, "value": value}))
```

and returns it with the `sha384:` prefix.

### `compute_event_digest(event_id, event_type, created_iso, entry_digests)`

Computes the event digest over canonical JSON containing:

- `created`
- `entry_digests`
- `event_id`
- `event_type`

## Adapter Interfaces

### `ImmutableLogAdapter`

Required methods:

- `submit_bundle(bundle: str, prev_log_id: str | None = None) -> tuple[str, str, Any]`
- `get_entry(log_id: str) -> Any`
- `traverse(end_log_id: str, count: int = 10) -> list[Any]`

Optional discovery helper:

- `find_entries_by_payload_hash(payload_hash: str) -> list[Any]`

The adapter contract is intentionally generic. `tlog` does not prescribe backend response schemas beyond what callers and adapters agree on.

### `LocalMRAdapter`

Required methods:

- `read(index: int) -> str`
- `extend(index: int, digest: str) -> tuple[str, str]`

This is an abstraction for a local measurement register surface. The package does not define one fixed platform policy.

## Example

```python
from datetime import UTC, datetime

from tlog import Entry, EventLog, Record, compute_entry_digest, compute_event_digest

entries = [
    Entry("artifact", "example.tar"),
    Entry("size", 1234),
]

record = Record(entries=entries)
created = datetime.now(UTC).isoformat()
entry_digests = [compute_entry_digest(item.key, item.value) for item in entries]
event_digest = compute_event_digest(
    event_id="evt-1",
    event_type="example.created",
    created_iso=created,
    entry_digests=entry_digests,
)

event = EventLog(
    event_id="evt-1",
    event_type="example.created",
    digest=event_digest,
    record=record,
    created=datetime.now(UTC),
)
```

## Non-Goals

The following are outside the `tlog` package API surface:

- service-side sequencing APIs
- queue mutation endpoints
- attestation export formats
- application-specific verification profiles
- any one repository's control-plane client
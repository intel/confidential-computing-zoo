## Context

TruCon serializes all chain-mutating operations (RTMR extend + SQLite INSERT + chain_state UPDATE) behind a `threading.Lock()` in a single-instance process (`--workers 1`). The tc_api side signs DSSE envelopes and POSTs to TruCon's `POST /commit` endpoint via HTTP.

If the HTTP response is lost (TCP timeout, connection reset), tc_api may retry the same commit. TruCon has no way to detect the duplicate — it extends RTMR again and inserts a second record. Because RTMR extend is a hardware operation that cannot be reversed, the measurement chain is permanently corrupted. All subsequent chain verification fails.

Current commit path (no dedup):
```
tc_api                             TruCon (_sequencer_lock)
  │                                  │
  │── POST /commit {bundle, ...} ──▶ │ read chain_state
  │                                  │ RTMR extend (irreversible)
  │                                  │ INSERT commit_queue
  │                                  │ UPDATE chain_state
  │◀── 200 {record_id, mr_value} ── │
  │    (response lost)               │
  │                                  │
  │── POST /commit {same bundle} ──▶ │ read chain_state
  │                                  │ RTMR extend AGAIN (corrupted!)
  │                                  │ INSERT duplicate record
```

## Goals / Non-Goals

**Goals:**
- Prevent duplicate RTMR extends when the same commit is retried.
- Return the original `CommitResponse` for duplicate requests without side effects.
- Maintain backward compatibility — callers without idempotency keys still work.
- Keep the change minimal and contained within the existing lock-based architecture.

**Non-Goals:**
- Content-based deduplication (intentionally identical events with different keys are allowed).
- Idempotency for non-commit endpoints (`GET /chain-state`, `GET /status`).
- Idempotency key expiration or TTL (keys persist with the record, which is in ephemeral tmpfs anyway).
- Observability metrics for idempotency hits (deferred to GAP-04).

## Decisions

### D1: Key generation strategy — random UUID per commit attempt

**Decision**: tc_api generates a random `idk-<uuid-hex-12>` key in `commit_record()` and includes it in every `POST /commit` payload.

**Alternatives considered**:
- *Content-derived key* (`sha256(chain_id + event_digest)`): Would silently deduplicate intentionally repeated identical events. Rejected because the architecture allows submitting the same event payload multiple times as separate records.
- *Caller-provided key*: Shifts idempotency responsibility to business endpoints. Rejected to avoid burdening every call site — the dedup boundary is the HTTP retry between tc_api and TruCon, not the business logic.

**Rationale**: A random key scoped to one `commit_record()` invocation ensures retries of the same HTTP request are deduplicated, while intentional re-submissions from separate `commit_record()` calls get distinct keys.

### D2: Idempotency check placement — inside the sequencer lock

**Decision**: The duplicate check (SQLite SELECT by `idempotency_key + chain_id`) is performed inside `_sequencer_lock`, before the RTMR extend.

```
with _sequencer_lock:
    existing = get_record_by_idempotency_key(key, chain_id)
    if existing:
        return cached CommitResponse    ← early return, no RTMR extend
    # proceed: RTMR extend → INSERT → UPDATE chain_state
```

**Alternatives considered**:
- *Check outside lock, then re-check inside*: Adds complexity for negligible performance gain. TruCon runs `--workers 1`, so at most one commit is ever in flight.

**Rationale**: Single check inside the lock eliminates TOCTOU races with zero performance impact given the single-worker deployment model.

### D3: Idempotency key is optional on TruCon API

**Decision**: `CommitRequest.idempotency_key: Optional[str] = None`. When omitted, deduplication is disabled for that request.

**Rationale**: Backward compatibility. tc_api always sends a key, but other potential internal callers (future Docktap integration) won't break if they don't yet.

### D4: FAILED duplicate behavior — return FAILED as-is

**Decision**: When a duplicate matches a record with `status=FAILED`, TruCon returns the FAILED record's data. The caller must generate a new idempotency key to retry with fresh intent.

**Alternatives considered**:
- *Delete FAILED record and re-attempt*: Contradicts the architecture principle that "FAILED records block subsequent submissions in the same chain until operator intervention."

### D5: UNIQUE constraint scoping

**Decision**: The `idempotency_key` column has a table-level UNIQUE constraint (not scoped to `chain_id`).

**Rationale**: A globally unique key (UUID-based) will never collide across chains. A simpler UNIQUE constraint avoids a composite index. NULL values are exempt from UNIQUE in SQLite, so legacy rows without keys don't conflict.

## Risks / Trade-offs

- **[Risk] tc_api crashes after generating the key but before sending the request** → No impact. The key is ephemeral in-memory. A new `commit_record()` call generates a new key. The lost key is never stored anywhere.

- **[Risk] TruCon instance lock file is stale after crash** → Not introduced by this change. Existing `fcntl.flock` mechanism handles this. Mentioned for completeness.

- **[Risk] Migration on large existing databases** → Mitigated by ephemeral storage model. The SQLite database lives in `/dev/shm/` and is recreated on VM reboot. Migration is a single `ALTER TABLE ADD COLUMN` which is instantaneous for the expected queue sizes (< 10K rows).

- **[Trade-off] No key expiration** → Keys persist for the lifetime of the record (until the tmpfs is destroyed on reboot). Acceptable because queue entries are transient by design — they either get CONFIRMED and submitted to Rekor, or FAILED for operator triage. No key-space exhaustion risk.

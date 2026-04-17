## Context

TruCon currently records trusted events in a per-chain commit queue with `chain_id` as the routing key. GAP-11 resolved chain assignment: Docktap extracts `tc.workload_id` from container labels and uses it as `chain_id`. However, TruCon has no concept of "instance" — it cannot answer which container instances belong to a workload or which events belong to a specific container lifecycle.

Current state:
- `commit_queue` has `chain_id` (= workload_id for Docktap events, "default" for unlabeled containers).
- Docktap's `workload_store.py` tracks `container_id → workload_id` locally in ephemeral tmpfs, but this is only used for chain routing — not queryable externally.
- There are no query endpoints beyond `GET /chain-state/{chain_id}` and `GET /status`.
- Architecture doc §5.2 defines a planned mapping model; open question Q-03 (canonical instance fields) is unresolved.

## Goals / Non-Goals

**Goals:**
- Resolve Q-03: define instance identity as full Docker `container_id` (64-character hex), one `create→rm` lifecycle = one instance.
- Store `instance_id` per commit record in TruCon's SQLite queue.
- Provide query endpoints for workload→instance and instance→event lookups.
- Keep `instance_id` as out-of-band routing metadata (like `chain_id`) — not inside the signed DSSE predicate.

**Non-Goals:**
- Cross-CVM workload aggregation (that belongs to an immutable-backend query layer).
- Pagination — event counts per instance within a single CVM lifecycle are bounded (create/start/stop/rm + REST events).
- Rich Entry type changes (FIX-04 is separate).
- Workload lifecycle management or orchestration (TruCon is a passive recorder).

## Decisions

### D1: instance_id = full Docker container_id

**Choice**: Use the full 64-character Docker container ID as `instance_id`.

**Alternatives considered**:
- Short ID (12 chars): collision risk in high-throughput environments, not worth the savings.
- workload_id + ordinal: requires TruCon to allocate and track ordinals — added state management for no real benefit since Docker already provides a unique identifier.
- Composite key (workload_id + container_id): unnecessary — container_id is globally unique within a Docker daemon; workload_id is a lookup dimension, not part of identity.

**Rationale**: Docker's container ID is globally unique, already available in every Docktap operation, and maps 1:1 to a container lifecycle (create→rm). No new identity allocation logic needed.

### D2: instance_id as optional CommitRequest metadata field

**Choice**: Add `instance_id: Optional[str] = None` to `CommitRequest`. Store it in `commit_queue.instance_id TEXT` column.

**Alternatives considered**:
- TruCon parses the DSSE payload to extract instance info: breaks the opaque-bundle principle — TruCon should not interpret signed payloads.
- Separate mapping registration endpoint (e.g., `POST /instances`): adds a two-phase protocol where the caller must register before committing — unnecessary complexity.

**Rationale**: Follows the same pattern as `chain_id` — caller-provided routing/correlation metadata that sits outside the cryptographic envelope. TruCon stores it for indexing without needing to understand the event payload.

### D3: Query endpoints on TruCon (not Docktap)

**Choice**: Three query endpoints served by TruCon:
1. `GET /workloads/{workload_id}/instances` — list instances with summary metadata.
2. `GET /instances/{instance_id}/events` — list events for a specific container lifecycle.
3. `GET /workloads/{workload_id}/events` — all events across all instances of a workload, ordered by sequence_num.

**Alternatives considered**:
- Query on Docktap side: Docktap is a proxy, not an audit service; its storage is ephemeral tmpfs lost on reboot.
- Generic filter endpoint (`GET /events?workload_id=X&instance_id=Y`): over-engineered for the expected query patterns; the three specific endpoints cover all audit use cases.

**Rationale**: TruCon is the single source of truth for committed events. It already has the SQLite database and REST API infrastructure. Queries are simple aggregations over `commit_queue` rows grouped by `chain_id` (= workload_id) and `instance_id`.

### D4: No separate mapping tables — derive from commit_queue

**Choice**: Query workload→instance and instance→event relationships directly from `commit_queue` using SQL aggregation (e.g., `SELECT DISTINCT instance_id ... GROUP BY`). No new SQLite tables.

**Alternatives considered**:
- Dedicated `workloads` and `instances` tables: adds write overhead on every commit (maintain two additional tables) and migration complexity.
- Materialized views: SQLite doesn't natively support them; simulated views add complexity without benefit at this scale.

**Rationale**: The commit_queue already contains `chain_id` and (after this change) `instance_id` per record. The expected data volume per CVM lifecycle is small (tens to hundreds of records). Aggregation queries are cheap. If performance becomes a concern later, an index on `(chain_id, instance_id)` suffices.

### D5: instance_id is nullable — REST events and legacy commits may omit it

**Choice**: `instance_id` is optional. Records without it are included in workload event queries but excluded from instance-specific queries.

**Rationale**: REST API callers (build/publish/launch flows) don't always have a container_id context. Backward compatibility with existing records (which have no instance_id) is preserved.

## Risks / Trade-offs

- **[R1] Ephemeral data**: All mapping data lives in TruCon's ephemeral SQLite (`/dev/shm/`). VM reboot loses all local query state. → Mitigation: This is by-design for CVM confidentiality. Post-reboot audit relies on immutable backend traversal (Rekor/on-chain), not local TruCon queries. Instance metadata is also embedded in the DSSE payload entries (operation_type, container info) — it can be reconstructed from the backend if needed.

- **[R2] No pagination**: For pathological workloads with thousands of container churn events, response sizes could grow. → Mitigation: Bounded by CVM lifetime and practical container counts. Add pagination later if needed (non-breaking — add optional `?limit=` / `?offset=` params).

- **[R3] instance_id is not authenticated/signed**: It's caller-asserted metadata outside the DSSE envelope. A malicious caller could provide a fake instance_id. → Mitigation: Same trust model as `chain_id` — TruCon trusts authenticated callers (service token). The DSSE payload itself carries the signed evidence; instance_id is a query convenience, not a trust anchor.

## Schema Changes

```sql
-- commit_queue gains one column:
ALTER TABLE commit_queue ADD COLUMN instance_id TEXT;

-- Index for efficient mapping queries:
CREATE INDEX IF NOT EXISTS idx_commit_queue_instance
    ON commit_queue (chain_id, instance_id);
```

## Response Models

```python
class InstanceSummary(BaseModel):
    instance_id: str
    first_event_at: str
    last_event_at: str
    event_count: int

class EventSummary(BaseModel):
    record_id: str
    event_id: Optional[str]
    sequence_num: int
    status: str
    created_at: str
    instance_id: Optional[str] = None
```

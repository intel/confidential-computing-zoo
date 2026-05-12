## Context

`GET /status` currently returns `QueueStatusResponse(queued_count, failed_count, next_sequence_num)` — a Pydantic model defined inline in `trucon/app.py`. The architecture defines two distinct data structures: `CommitQueueStatus` (worker-facing queue summary) and `LatestState` (audit-facing chain snapshot). Both exist as dataclasses in `tlog/types.py` but neither is served by the API.

After GAP-06 introduced granular lifecycle states, `get_queue_stats()` returns 5 fields but the 3-field `QueueStatusResponse` silently drops `submitting_count`, `failed_retryable_count`, and `failed_terminal_count`. The `tlog_client.py` consumer hardcodes `next_record_id=None` because the endpoint never provides it.

The SQLite `chain_state` table stores `head_log_id` and `mr_value` per chain, and `commit_queue` stores `event_id` per record — all data needed for `LatestState` is already present. The default chain is `'default'`.

## Goals / Non-Goals

**Goals:**
- `GET /status` returns fields matching the `CommitQueueStatus` contract plus GAP-06 granular counts
- New `GET /state` endpoint returns `LatestState` for the default chain
- `tlog_client.py` properly consumes both endpoints and populates all fields
- Remove the orphaned `QueueStatusResponse` model

**Non-Goals:**
- Multi-chain `GET /state` with `chain_id` parameter (future extension)
- Metrics instrumentation on the new endpoint (deferred to GAP-04)
- Backward-compatible shim for the old `GET /status` shape

## Decisions

### D1: Separate endpoints (B) over merged response

`GET /status` stays lightweight for high-frequency daemon polling (simple COUNT queries). `GET /state` performs heavier queries (chain_state join + event_id scan) and is intended for low-frequency audit/operational use. Merging them would add unnecessary overhead to every daemon poll cycle.

**Alternative considered**: Single `GET /status` returning `{ queue: ..., state: ... }` — rejected because the daemon never needs chain snapshot data, and the query cost scales differently.

### D2: Extend CommitQueueStatus with granular counts

The architecture's `CommitQueueStatus` has 3 fields. We extend the Pydantic response model to also include `submitting_count`, `failed_retryable_count`, and `failed_terminal_count` so the data already computed by `get_queue_stats()` is not discarded. The base 3 fields (`has_queued_records`, `queued_record_count`, `next_record_id`) match the architecture exactly.

**Alternative considered**: Strict 3-field response — rejected because GAP-06 already computes granular counts and dropping them loses observability.

### D3: Database returns record_id alongside sequence_num

`get_queue_stats()` currently finds the minimum pending sequence_num but not the corresponding `record_id`. We'll add a single query to fetch the `record_id` of the min-sequence pending record, returning both `next_record_id` and `next_sequence_num` (the latter for internal daemon use).

### D4: LatestState queries chain_state + commit_queue

New `get_latest_state(chain_id)` database function:
1. Read `chain_state` row → `head_log_id` (= `latest_confirmed_log_id`), `mr_value` (= `latest_mr_value`)
2. Count PENDING records → `pending_record_count`
3. Select PENDING `event_id` values → `pending_event_ids`

If no `chain_state` row exists (empty chain), return all-null/zero defaults.

### D5: Default chain is `'default'`

`GET /state` with no parameter queries `chain_id = 'default'`, matching the SQLite column default. Future multi-chain support would add an optional `chain_id` query parameter.

## Risks / Trade-offs

- **[Breaking API]** → Acceptable: no known external consumers; `tlog_client.py` is the only caller and will be updated simultaneously. Document the change in proposal.
- **[LatestState performance on large queues]** → The pending event_id scan is O(n) on pending records. Mitigated: pending queues are expected to be small (daemon drains them); if needed, add a LIMIT later.
- **[Default chain assumption]** → If a deployment uses non-default chain names exclusively, `GET /state` returns empty. Mitigated: acceptable for current single-chain usage; multi-chain support is a future extension.

## Why

The `GET /status` endpoint returns a `QueueStatusResponse` with fields (`queued_count`, `failed_count`, `next_sequence_num`) that don't match the architecture's `CommitQueueStatus` contract (`has_queued_records`, `queued_record_count`, `next_record_id`). The `LatestState` data structure — a compact chain snapshot with `latest_confirmed_log_id`, `pending_event_ids`, and `latest_mr_value` — has no endpoint at all. Additionally, after GAP-06 introduced granular lifecycle states, `get_queue_stats()` returns 5 fields but the endpoint model only accepts 3, silently discarding `submitting_count`, `failed_retryable_count`, and `failed_terminal_count`.

## What Changes

- **BREAKING**: Replace `QueueStatusResponse` with architecture-aligned `CommitQueueStatus` on `GET /status`. Fields change from `(queued_count, failed_count, next_sequence_num)` to `(has_queued_records, queued_record_count, next_record_id)` plus granular state counts.
- Add new `GET /state` endpoint returning `LatestState` for the default chain (chain snapshot: `latest_confirmed_log_id`, `pending_record_count`, `pending_event_ids`, `latest_mr_value`).
- Update `get_queue_stats()` in the database layer to also return `next_record_id` (not just `next_sequence_num`).
- Add a new database helper to build `LatestState` from `chain_state` and `commit_queue` tables.
- Update `tlog_client.py`'s `get_commit_queue_status()` to consume the new response shape and populate `next_record_id` properly (currently hardcoded to `None`).
- Remove the stale `QueueStatusResponse` Pydantic model from `trucon/app.py`.

## Capabilities

### New Capabilities
- `trucon-latest-state`: Defines the `GET /state` endpoint contract returning `LatestState` for the default chain, including field semantics, query behavior, and empty-chain edge cases.

### Modified Capabilities
- `tlog-embedded-submitter`: The submit daemon's status polling may reference the updated queue stats shape. No requirement-level change — implementation only.

## Impact

- **API (breaking)**: `GET /status` response shape changes. Any external consumer of this endpoint must update field names.
- **Code**: `src/tc_api/trucon/app.py` (endpoint + model), `src/tc_api/trucon/database.py` (query helpers), `src/tc_api/tlog_client.py` (client mapping), `src/tc_api/tlog/types.py` (type verification).
- **Tests**: `tests/test_sequencer_refactor.py` (test_get_queue_stats assertions), any integration tests hitting `/status`.
- **No new dependencies**: Uses existing SQLite tables and chain_state data.

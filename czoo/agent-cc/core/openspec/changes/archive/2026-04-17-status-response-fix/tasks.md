## 1. Database Layer

- [x] 1.1 Update `get_queue_stats()` in `database.py` to also return `next_record_id` (SELECT record_id from min-sequence pending record) alongside existing `next_sequence_num`
- [x] 1.2 Add `get_latest_state(chain_id)` function in `database.py` that queries `chain_state` for `head_log_id`/`mr_value` and `commit_queue` for pending record count and event_ids

## 2. Response Models

- [x] 2.1 Replace `QueueStatusResponse` in `trucon/app.py` with new `CommitQueueStatusResponse` Pydantic model: `has_queued_records`, `queued_record_count`, `next_record_id`, `submitting_count`, `failed_retryable_count`, `failed_terminal_count`
- [x] 2.2 Add `LatestStateResponse` Pydantic model in `trucon/app.py`: `latest_confirmed_log_id`, `pending_record_count`, `pending_event_ids`, `latest_mr_value`

## 3. Endpoints

- [x] 3.1 Update `GET /status` handler to use `CommitQueueStatusResponse`, compute `has_queued_records` from `queued_count > 0`, map `next_record_id` from updated `get_queue_stats()`
- [x] 3.2 Add `GET /state` endpoint calling `get_latest_state('default')` and returning `LatestStateResponse`

## 4. Client Update

- [x] 4.1 Update `tlog_client.py` `get_commit_queue_status()` to consume new `GET /status` field names and populate `next_record_id` from response instead of hardcoding `None`

## 5. Tests — New

- [x] 5.1 Test: `GET /status` returns `CommitQueueStatusResponse` with all 6 fields for mixed queue state
- [x] 5.2 Test: `GET /status` returns correct defaults for empty queue
- [x] 5.3 Test: `GET /status` `next_record_id` matches the lowest-sequence pending record
- [x] 5.4 Test: `GET /state` returns correct `LatestState` for default chain with confirmed + pending records
- [x] 5.5 Test: `GET /state` returns null/zero defaults for empty chain
- [x] 5.6 Test: `get_latest_state()` database function returns correct data
- [x] 5.7 Test: `tlog_client.get_commit_queue_status()` maps new fields correctly

## 6. Tests — Update Existing

- [x] 6.1 Update `test_sequencer_refactor.py` `test_get_queue_stats` assertions to match new return shape (add `next_record_id`)
- [x] 6.2 Run full regression: 73/73 tests pass

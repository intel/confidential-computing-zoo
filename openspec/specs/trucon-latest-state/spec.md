## ADDED Requirements

### Requirement: GET /status returns CommitQueueStatus
The `GET /status` endpoint SHALL return a JSON object with the following fields: `has_queued_records` (bool), `queued_record_count` (int), `next_record_id` (string or null), `submitting_count` (int), `failed_retryable_count` (int), `failed_terminal_count` (int), `total_retry_count` (int). The `has_queued_records` field SHALL be `true` when `queued_record_count > 0`. The `next_record_id` field SHALL contain the `record_id` of the pending record with the lowest `sequence_num` that has `rtmr_extended = true`, or `null` if no such record exists. The `total_retry_count` field SHALL contain the sum of `retry_count` across all records in the commit queue.

#### Scenario: Queue with pending and failed records
- **WHEN** the commit queue contains 2 PENDING records, 1 SUBMITTING record, 1 FAILED_RETRYABLE record, and 1 FAILED_TERMINAL record, with total retry counts summing to 7
- **THEN** the response SHALL include `has_queued_records: true`, `queued_record_count: 2`, `submitting_count: 1`, `failed_retryable_count: 1`, `failed_terminal_count: 1`, `next_record_id` set to the record_id of the lowest-sequence PENDING record, and `total_retry_count: 7`

#### Scenario: Empty queue
- **WHEN** the commit queue contains no records
- **THEN** the response SHALL include `has_queued_records: false`, `queued_record_count: 0`, `next_record_id: null`, `submitting_count: 0`, `failed_retryable_count: 0`, `failed_terminal_count: 0`, `total_retry_count: 0`

#### Scenario: No pending but failed records exist
- **WHEN** the commit queue contains only FAILED_TERMINAL records and no PENDING records
- **THEN** `has_queued_records` SHALL be `false`, `queued_record_count` SHALL be `0`, and `next_record_id` SHALL be `null`

### Requirement: GET /state returns LatestState for default chain
The `GET /state` endpoint SHALL return a JSON object with the following fields: `latest_confirmed_log_id` (string or null), `pending_record_count` (int), `pending_event_ids` (array of strings), `latest_mr_value` (string or null). The endpoint SHALL query the `chain_state` table for chain_id `'default'` to obtain `latest_confirmed_log_id` (from `head_log_id`) and `latest_mr_value` (from `mr_value`). It SHALL query `commit_queue` for PENDING records in the default chain to obtain `pending_record_count` and `pending_event_ids`.

#### Scenario: Chain with confirmed and pending records
- **WHEN** the default chain has a confirmed head with `log_id = "rekor-abc"` and `mr_value = "0xdead"`, and 2 pending records with event_ids `["evt-1", "evt-2"]`
- **THEN** the response SHALL include `latest_confirmed_log_id: "rekor-abc"`, `latest_mr_value: "0xdead"`, `pending_record_count: 2`, `pending_event_ids: ["evt-1", "evt-2"]`

#### Scenario: Empty chain (no records ever committed)
- **WHEN** no `chain_state` row exists for `'default'` and no pending records exist
- **THEN** the response SHALL include `latest_confirmed_log_id: null`, `latest_mr_value: null`, `pending_record_count: 0`, `pending_event_ids: []`

#### Scenario: All records confirmed (nothing pending)
- **WHEN** the default chain has confirmed records but no pending records
- **THEN** `pending_record_count` SHALL be `0`, `pending_event_ids` SHALL be `[]`, and `latest_confirmed_log_id` and `latest_mr_value` SHALL reflect the chain head

### Requirement: tlog_client consumes new response shapes
The `get_commit_queue_status()` method in `tlog_client.py` SHALL populate all `CommitQueueStatus` fields from the `GET /status` response, including `next_record_id`. It SHALL NOT hardcode any field to `None`.

#### Scenario: Client maps status response to CommitQueueStatus
- **WHEN** `get_commit_queue_status()` receives a response with `queued_record_count: 3` and `next_record_id: "rec-abc"`
- **THEN** the returned `CommitQueueStatus` SHALL have `has_queued_records: True`, `queued_record_count: 3`, `next_record_id: "rec-abc"`

### Requirement: QueueStatusResponse model removed
The `QueueStatusResponse` Pydantic model SHALL be removed from `trucon/app.py`. The `GET /status` endpoint SHALL use a new response model matching the `CommitQueueStatus` field set.

#### Scenario: Old model no longer importable
- **WHEN** code attempts to import `QueueStatusResponse` from `trucon/app.py`
- **THEN** the import SHALL fail (the class no longer exists)

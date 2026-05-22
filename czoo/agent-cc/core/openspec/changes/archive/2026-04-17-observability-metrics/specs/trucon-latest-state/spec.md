## MODIFIED Requirements

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

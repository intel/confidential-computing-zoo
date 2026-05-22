## ADDED Requirements

### Requirement: TruCon SHALL provide trusted event lifecycle APIs
TruCon SHALL expose internal APIs that support record initialization, ordered entry append, commit, submission, and lifecycle status querying for trusted events.

#### Scenario: Initialize trusted record context
- **WHEN** a REST API worker or Docktap worker requests record initialization
- **THEN** TruCon returns a unique record identifier and context metadata used for subsequent entry append and commit operations

#### Scenario: Append ordered entries to record
- **WHEN** a caller submits an entry for an existing open record
- **THEN** TruCon persists the entry in deterministic order for that record and returns updated entry count metadata

#### Scenario: Commit record for asynchronous submission
- **WHEN** a caller commits a record
- **THEN** TruCon finalizes the record digest, marks the record as queued for submission, and returns commit acknowledgement without requiring immediate backend confirmation

### Requirement: TruCon SHALL manage queue-driven submission state transitions
TruCon SHALL maintain explicit lifecycle states for committed records and SHALL handle retries and state transitions during backend submission.

#### Scenario: Successful backend confirmation
- **WHEN** a queued record is submitted successfully to immutable backend
- **THEN** TruCon marks the record as confirmed and stores backend confirmation metadata

#### Scenario: Retryable backend failure
- **WHEN** backend submission fails due to retryable failure
- **THEN** TruCon marks the record as retryable pending state and schedules retry according to configured retry policy

#### Scenario: State query for queued records
- **WHEN** a caller requests queue or record submission status
- **THEN** TruCon returns current lifecycle state and relevant status metadata for that record

### Requirement: TruCon SHALL enforce idempotent trusted event ingestion
TruCon SHALL enforce idempotency for event commit requests so duplicate retries from callers do not create duplicate committed records.

#### Scenario: Duplicate commit request with same event identity
- **WHEN** the same event identity is committed more than once
- **THEN** TruCon returns the existing committed record outcome instead of creating a second committed record

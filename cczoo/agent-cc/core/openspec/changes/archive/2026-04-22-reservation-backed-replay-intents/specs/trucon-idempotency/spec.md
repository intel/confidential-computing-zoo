## MODIFIED Requirements

### Requirement: TruCon detects duplicate commits by idempotency key
The TruCon reservation-backed commit flow SHALL accept an optional `idempotency_key` for the full lifecycle of a logical record. When a request includes an `idempotency_key` that matches an existing reservation or committed record in the same `chain_id`, TruCon SHALL return the existing lifecycle result instead of allocating a competing reservation or inserting a second queue record.

#### Scenario: First reservation with idempotency key
- **WHEN** TruCon receives a reservation request with an `idempotency_key` that does not exist for that `chain_id`
- **THEN** TruCon SHALL allocate a new intent and persist the `idempotency_key` with that intent

#### Scenario: Duplicate reservation returns existing active intent
- **WHEN** TruCon receives a reservation request with an `idempotency_key` that already maps to an `ACTIVE` intent for the same `chain_id`
- **THEN** TruCon SHALL return the original `intent_token` and predecessor contract without allocating a new reservation

#### Scenario: Duplicate lifecycle request after successful commit returns cached response
- **WHEN** TruCon receives a reservation or commit retry with an `idempotency_key` that already produced a committed queue record for the same `chain_id`
- **THEN** TruCon SHALL return the original commit result without inserting a new record

#### Scenario: Commit without idempotency key
- **WHEN** TruCon receives a reservation-backed operation without an `idempotency_key` (field omitted or null)
- **THEN** TruCon SHALL proceed without lifecycle deduplication

### Requirement: Idempotency check is atomic within the sequencer lock
The lifecycle idempotency lookup for reservation-backed records SHALL be performed inside the sequencer lock before a new intent is minted. This SHALL prevent TOCTOU races where two concurrent retries with the same key both allocate reservations.

#### Scenario: Concurrent identical reservation requests serialize correctly
- **WHEN** two reservation requests with the same `idempotency_key` arrive concurrently for the same `chain_id`
- **THEN** the first request to acquire the sequencer lock SHALL create the intent and the second SHALL detect the duplicate lifecycle state and return the cached result

### Requirement: Idempotency key stored in commit_queue with UNIQUE constraint
The database SHALL persist the `idempotency_key` for reservation-backed records and SHALL enforce uniqueness for the active lifecycle of a logical commit within a chain. The persisted state SHALL be sufficient to return either the original `intent_token` or the original commit result on retry after process restart.

#### Scenario: Fresh database supports lifecycle idempotency persistence
- **WHEN** TruCon initializes a fresh database
- **THEN** the database schema SHALL include the columns and indexes needed to look up an existing lifecycle by `chain_id` and `idempotency_key`

#### Scenario: Retry after restart returns existing lifecycle state
- **WHEN** TruCon restarts after persisting an active or consumed lifecycle for a given `chain_id` and `idempotency_key`
- **THEN** a retry with that same key SHALL resolve to the existing intent or existing commit result rather than creating a duplicate record
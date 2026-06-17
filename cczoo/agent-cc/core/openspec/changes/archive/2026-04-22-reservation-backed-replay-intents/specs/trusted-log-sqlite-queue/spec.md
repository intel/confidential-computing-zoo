## MODIFIED Requirements

### Requirement: Lossy Crash Recovery
The queue SHALL perform conditional crash recovery on TruCon startup. Records with `rtmr_extended=TRUE` and `status=PENDING` SHALL be retained for immutable-backend submission. Records with `rtmr_extended=FALSE` SHALL be deleted. The `chain_state` table SHALL be rebuilt from the highest `sequence_num` committed record with `rtmr_extended=TRUE`. The `commit_intents` table SHALL also be recovered on startup: intents already marked `CONSUMED` SHALL be retained as idempotency history, intents in non-terminal active states whose `expires_at` has passed SHALL be marked `EXPIRED`, and any chain-level active-intent gate SHALL be recalculated from the recovered persisted intent rows. Upon VM reboot (implied by `/dev/shm` reset), all queue data vanishes, retaining cryptographic validity on subsequent commits because RTMR registers also reset.

#### Scenario: Submitting event post-crash
- **WHEN** the VM completely restarts and initiates the hardware TD bounds anew
- **THEN** previous uncommitted local events vanish cryptographically, retaining 100% cryptographic validity logic on subsequent commits

#### Scenario: Process restart with RTMR-extended pending records
- **WHEN** the TruCon process restarts and finds records with `rtmr_extended=TRUE` and `status=PENDING`
- **THEN** those records SHALL be retained in the queue for the submit daemon to process

#### Scenario: Process restart with non-extended records
- **WHEN** the TruCon process restarts and finds records with `rtmr_extended=FALSE`
- **THEN** those records SHALL be deleted from the queue

#### Scenario: Expired active intents are closed during recovery
- **WHEN** TruCon restarts and finds `ACTIVE` intent rows whose `expires_at` is in the past
- **THEN** those intents SHALL be marked `EXPIRED` before new reservations are accepted for the same chain

### Requirement: Extended commit_queue schema
The `commit_queue` table SHALL include the following columns: `record_id` (TEXT PRIMARY KEY), `event_id` (TEXT), `chain_id` (TEXT NOT NULL), `payload` (TEXT NOT NULL), `status` (TEXT NOT NULL), `rtmr_extended` (BOOLEAN DEFAULT FALSE), `log_id` (TEXT), `prev_log_id` (TEXT), `mr_value` (TEXT), `sequence_num` (INTEGER NOT NULL), `event_digest` (TEXT), `prev_event_digest` (TEXT), `prev_lookup_hash` (TEXT), `idempotency_key` (TEXT), `intent_token` (TEXT), `retry_count` (INTEGER DEFAULT 0), `confirmed_at` (TEXT), `updated_at` (TEXT NOT NULL). The database SHALL also include a durable `commit_intents` table containing at least `intent_token`, `chain_id`, `idempotency_key`, `status`, `sequence_num`, `prev_event_digest`, `prev_lookup_hash`, `expires_at`, `created_at`, and `updated_at` so reservation state survives process restart.

#### Scenario: Record inserted with replay metadata
- **WHEN** TruCon inserts a reservation-backed commit record into the queue
- **THEN** the row SHALL persist the reserved `event_digest`, `prev_event_digest`, `prev_lookup_hash`, `idempotency_key`, and `intent_token` alongside `chain_id`, `sequence_num`, and `rtmr_extended`

#### Scenario: Intent row persisted on reservation
- **WHEN** TruCon allocates a new commit intent
- **THEN** the `commit_intents` table SHALL persist the reserved predecessor contract and expiry metadata before the reservation response is returned to the caller

## ADDED Requirements

### Requirement: Schema migration adds durable reservation storage
On first startup with an existing database, TruCon SHALL create the `commit_intents` table if it is absent and SHALL add any new replay metadata columns required by the reservation-backed flow to `commit_queue` without destroying existing commit history.

#### Scenario: Migrate legacy database to reservation-backed schema
- **WHEN** TruCon starts with a database created before commit intents were introduced
- **THEN** it SHALL create the `commit_intents` table and SHALL add missing replay metadata columns needed for reservation-backed commits before serving new reservation requests
## ADDED Requirements

### Requirement: TruCon reserves a signed predecessor contract before replayable commits
TruCon SHALL expose a reservation endpoint for replayable records. A successful reservation SHALL return a single-use opaque `intent_token` and the exact predecessor contract that the caller must sign: `chain_id`, `sequence_num`, `prev_event_digest`, `prev_lookup_hash`, and `expires_at`.

#### Scenario: Reserve next sequence on existing chain
- **WHEN** a caller reserves a commit intent for a chain that already has a confirmed or pending head and no conflicting active intent
- **THEN** TruCon SHALL allocate the next `sequence_num`, SHALL derive `prev_event_digest` and `prev_lookup_hash` from the current chain head, SHALL persist an `ACTIVE` intent row, and SHALL return that contract with an `intent_token`

#### Scenario: Reserve baseline intent for a new chain
- **WHEN** a caller reserves a baseline intent for a chain that does not yet exist
- **THEN** TruCon SHALL return `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null` in the reserved predecessor contract

### Requirement: Only one active intent per chain in the initial reservation model
TruCon SHALL permit at most one `ACTIVE` commit intent per `chain_id` in the initial implementation. A later reservation attempt for the same chain SHALL not mint a competing sequence slot until the active intent is consumed, cancelled, or expired.

#### Scenario: Conflicting active intent blocks second reservation
- **WHEN** a second caller requests a reservation for the same `chain_id` while an `ACTIVE` intent already exists for that chain
- **THEN** TruCon SHALL return an explicit conflict response and SHALL NOT allocate a second `sequence_num`

### Requirement: Commit consumes the reserved intent only after bundle validation
The final TruCon `/commit` path for replayable records SHALL accept `intent_token` together with the signed bundle and SHALL validate that the signed payload matches the reserved `chain_id`, `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` before inserting a queue record or advancing chain state.

#### Scenario: Matching bundle consumes intent
- **WHEN** `/commit` receives a signed bundle whose signed predecessor fields exactly match the reserved contract for the supplied `intent_token`
- **THEN** TruCon SHALL insert the queue record with the reserved sequence metadata, SHALL update the chain head, SHALL mark the intent `CONSUMED`, and SHALL return the committed `record_id` and `sequence_num`

#### Scenario: Bundle mismatch rejects commit
- **WHEN** `/commit` receives a signed bundle whose predecessor fields differ from the reserved contract for the supplied `intent_token`
- **THEN** TruCon SHALL reject the request, SHALL leave the intent unconsumed or failed according to implementation policy, and SHALL NOT insert a queue record for that attempt

### Requirement: Intent tokens expire and cannot be reused after terminal state
Each commit intent SHALL carry a server-defined expiry time. An expired, cancelled, or already consumed `intent_token` SHALL NOT be accepted for a new commit.

#### Scenario: Expired intent rejected
- **WHEN** a caller submits `/commit` with an `intent_token` whose persisted intent row is past `expires_at`
- **THEN** TruCon SHALL reject the commit and SHALL NOT insert a queue record

#### Scenario: Consumed intent cannot be replayed
- **WHEN** a caller reuses an `intent_token` that has already been marked `CONSUMED`
- **THEN** TruCon SHALL return the original commit result through idempotency handling or an explicit duplicate response and SHALL NOT create a second queue record
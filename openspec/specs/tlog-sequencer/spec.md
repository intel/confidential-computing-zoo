## Purpose

Define TruCon sequencer responsibilities for crash recovery and reservation-backed sequence allocation.

## Requirements

### Requirement: Crash recovery on startup
On startup, TruCon SHALL scan `commit_queue` for records requiring recovery. Records with `rtmr_extended = FALSE` or NULL SHALL be deleted (incomplete commits). Records with status `SUBMITTING` SHALL be reset to `PENDING` (interrupted submission). Recovery SHALL complete before the submit daemon begins processing.

#### Scenario: SUBMITTING records reset on startup
- **WHEN** TruCon starts and the `commit_queue` contains records with status `SUBMITTING`
- **THEN** those records SHALL be updated to status `PENDING` before the submit daemon starts

#### Scenario: Incomplete commits deleted on startup
- **WHEN** TruCon starts and the `commit_queue` contains records with `rtmr_extended = FALSE` or NULL
- **THEN** those records SHALL be deleted from the queue

### Requirement: Sequencing contract is allocated during reservation
TruCon SHALL allocate replay ordering inputs during the reservation step rather than during the final `/commit` enqueue step. The sequencing decision for a replayable record SHALL consist of `sequence_num`, `prev_event_digest`, and `prev_lookup_hash` derived while the sequencer lock is held.

#### Scenario: Concurrent reservations serialize on one chain
- **WHEN** two callers concurrently request reservations for the same `chain_id`
- **THEN** the caller that acquires the sequencer lock first SHALL receive the next available predecessor contract and the later caller SHALL observe the resulting active-intent state instead of a second independent allocation

### Requirement: Final commit validates but does not assign sequence inputs
For reservation-backed records, TruCon `/commit` SHALL validate the signed bundle against the already-reserved predecessor contract and SHALL NOT compute or overwrite `sequence_num`, `prev_event_digest`, or `prev_lookup_hash` during final commit.

#### Scenario: Commit preserves reserved sequence number
- **WHEN** a caller submits `/commit` for a valid reserved intent
- **THEN** the persisted queue record SHALL use the `sequence_num` that was allocated during reservation and SHALL NOT receive a newly assigned sequence at commit time

### Requirement: Active reservations gate later sequencing on the same chain
While a chain has an `ACTIVE` commit intent, TruCon SHALL treat that reservation as the outstanding next sequence slot for that chain and SHALL NOT allocate a later slot on the same chain until the active intent reaches a terminal state.

#### Scenario: Reservation expiry reopens sequencing
- **WHEN** the only active intent for a chain expires or is cancelled before final commit
- **THEN** a later reservation request for that same chain SHALL be allowed to allocate the next sequence slot for the still-current committed head

## REMOVED Requirements

### Requirement: Lazy Event Log 0 creation for new non-default chains
**Reason**: TruCon can no longer invent Event Log 0 inside `/commit` once baseline predecessor fields must be signed before enqueue. Baseline creation must move to the same reservation-backed sign-and-consume flow used by later replayable records.
**Migration**: Bootstrap a new chain by obtaining the baseline snapshot, reserving a baseline intent, signing Event Log 0 with `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`, and then calling `POST /init-chain` before the first business commit is enqueued.

## MODIFIED Requirements

### Requirement: Chain initialization endpoint
TruCon SHALL expose `POST /init-chain` accepting `{chain_id, init_token, intent_token, signed_bundle, pub_key}` for baseline creation. It SHALL verify the `init_token` is valid, SHALL verify that the supplied `intent_token` resolves to a valid baseline reservation for `chain_id`, SHALL validate that the signed baseline bundle matches the reserved predecessor contract, and SHALL then insert the baseline record with `sequence_num=1` and initialize `chain_state`. The RTMR SHALL NOT be extended for this record.

#### Scenario: Successful chain initialization
- **WHEN** tc_api calls `POST /init-chain` with a valid `init_token`, a valid baseline `intent_token`, and a signed DSSE bundle whose predecessor fields match the reserved baseline contract
- **THEN** TruCon SHALL insert Event Log 0 into `commit_queue` with `sequence_num=1`, `rtmr_extended=FALSE`, and `status=PENDING`, SHALL initialize `chain_state` for the chain, SHALL mark the baseline intent consumed, and SHALL return `{record_id, sequence_num}` with HTTP 200

#### Scenario: Invalid or expired init_token
- **WHEN** tc_api calls `POST /init-chain` with an invalid or already-used `init_token`
- **THEN** TruCon SHALL return HTTP 400 with a descriptive error

#### Scenario: Invalid baseline intent
- **WHEN** tc_api calls `POST /init-chain` with an `intent_token` that is invalid, expired, already consumed, or not reserved for baseline creation on that `chain_id`
- **THEN** TruCon SHALL return an error and SHALL NOT initialize the chain

#### Scenario: Concurrent init race
- **WHEN** two tc_api workers both attempt to initialize the same `chain_id`
- **THEN** the first successful call SHALL create Event Log 0 and the second SHALL receive HTTP 409 or the cached idempotent result rather than creating a second baseline

## ADDED Requirements

### Requirement: New non-default chains bootstrap baseline before first business event
For a previously unseen non-`default` chain, the first replayable business flow SHALL create Event Log 0 through the reservation-backed initialization path before the first business event is committed on that chain.

#### Scenario: First workload commit bootstraps signed baseline first
- **WHEN** a producer emits the first replayable event for a previously unseen non-`default` chain
- **THEN** the system SHALL complete baseline snapshot, baseline reservation, Event Log 0 signing, and `POST /init-chain` successfully before it enqueues the first business record for that chain

#### Scenario: Baseline creation failure rejects first business event
- **WHEN** the baseline bootstrap for a new non-`default` chain fails before Event Log 0 is initialized
- **THEN** the triggering business or runtime event SHALL be rejected and SHALL NOT be persisted onto a chain without a baseline anchor

### Requirement: Event Log 0 uses the same signed predecessor contract as later records
Event Log 0 SHALL carry explicit signed predecessor fields using the reservation-backed replay contract rather than a special unsigned insertion path.

#### Scenario: Baseline payload uses null predecessor contract
- **WHEN** tc_api signs Event Log 0 for a newly created chain
- **THEN** the signed payload SHALL include `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`
## Purpose

Define the required initialization and baseline semantics for trusted-log chains, including explicit Event Log 0 creation and startup initialization behavior.

## Requirements

### Requirement: New non-default chains bootstrap baseline before first business event
For a previously unseen non-`default` chain, the first replayable business flow SHALL create Event Log 0 through the reservation-backed initialization path before the first business event is committed on that chain.

#### Scenario: First workload commit bootstraps signed baseline first
- **WHEN** a producer emits the first replayable event for a previously unseen non-`default` chain
- **THEN** the system SHALL complete baseline snapshot, baseline reservation, Event Log 0 signing, and `POST /init-chain` successfully before it enqueues the first business record for that chain

#### Scenario: Baseline creation failure rejects first business event
- **WHEN** the baseline bootstrap for a new non-`default` chain fails before Event Log 0 is initialized
- **THEN** the triggering business or runtime event SHALL be rejected and SHALL NOT be persisted onto a chain without a baseline anchor

## ADDED Requirements

### Requirement: Baseline snapshot endpoint
TruCon SHALL expose `GET /init-chain/{chain_id}/baseline` that reads the current RTMR[2] value (without extending it) and computes the SHA-384 digest of the raw CCEL binary. The endpoint SHALL return `{rtmr_value, ccel_digest, init_token}`. If the chain already exists, the endpoint SHALL return HTTP 409.

#### Scenario: Successful baseline snapshot
- **WHEN** tc_api calls `GET /init-chain/{chain_id}/baseline` for a chain that does not yet exist
- **THEN** TruCon reads RTMR[2], computes CCEL digest, generates an opaque `init_token`, and returns `{rtmr_value, ccel_digest, init_token}` with HTTP 200

#### Scenario: Chain already exists
- **WHEN** tc_api calls `GET /init-chain/{chain_id}/baseline` for a chain that already has a `chain_state` entry
- **THEN** TruCon returns HTTP 409 with a descriptive error body

#### Scenario: Non-TEE environment
- **WHEN** TruCon is running without TDX hardware (no RTMR sysfs)
- **THEN** `rtmr_value` is null, `ccel_digest` is null, and the `init_token` is still generated

### Requirement: Chain initialization endpoint
TruCon SHALL expose `POST /init-chain` accepting `{chain_id, init_token, intent_token, signed_bundle, pub_key}` for baseline creation. It SHALL verify the `init_token` is valid, SHALL verify that the supplied `intent_token` resolves to a valid baseline reservation for `chain_id`, SHALL validate that the signed baseline bundle matches the reserved predecessor contract, SHALL persist Event Log 0 owner-attestation material sufficient to prove that `pub_key` was declared by the approved baseline initialization context, and SHALL then insert the baseline record with `sequence_num=1` and initialize `chain_state`. The RTMR SHALL NOT be extended for this record.

#### Scenario: Successful chain initialization
- **WHEN** tc_api calls `POST /init-chain` with a valid `init_token`, a valid baseline `intent_token`, and a signed DSSE bundle whose predecessor fields match the reserved baseline contract
- **THEN** TruCon SHALL insert Event Log 0 into `commit_queue` with `sequence_num=1`, `rtmr_extended=FALSE`, and `status=PENDING`, SHALL initialize `chain_state` for the chain, SHALL persist the owner-attestation material associated with the declared `pub_key`, SHALL mark the baseline intent consumed, and SHALL return `{record_id, sequence_num}` with HTTP 200

#### Scenario: Invalid or expired init_token
- **WHEN** tc_api calls `POST /init-chain` with an invalid or already-used `init_token`
- **THEN** TruCon SHALL return HTTP 400 with a descriptive error

#### Scenario: Invalid baseline intent
- **WHEN** tc_api calls `POST /init-chain` with an `intent_token` that is invalid, expired, already consumed, or not reserved for baseline creation on that `chain_id`
- **THEN** TruCon SHALL return an error and SHALL NOT initialize the chain

#### Scenario: Concurrent init race
- **WHEN** two tc_api workers both call `POST /init-chain` for the same `chain_id`
- **THEN** the first successful call SHALL create Event Log 0 and the second SHALL receive HTTP 409 or the cached idempotent result rather than creating a second baseline

### Requirement: Event Log 0 signed with chain owner key declaration
tc_api SHALL establish a durable chain owner public key at Event Log 0 and SHALL treat that key as the single long-term chain owner for later replayable writes. Event Log 0 SHALL include the owner public key in the baseline payload and SHALL persist owner-attestation material proving that the declared key belongs to the approved initialization context. The private key corresponding to that owner public key SHALL NOT be treated as an immediately discarded ephemeral bootstrap key.

#### Scenario: Owner key declaration included in baseline
- **WHEN** tc_api constructs Event Log 0 during chain initialization
- **THEN** the baseline payload SHALL include the declared owner public key and the persisted baseline contract SHALL identify it as the chain's single owner key

#### Scenario: Owner key is not modeled as discarded baseline-only state
- **WHEN** Event Log 0 has been signed and submitted via `POST /init-chain`
- **THEN** the system SHALL preserve semantics that the declared owner key remains authoritative for later replayable writes rather than documenting the key as an immediately discarded ephemeral baseline artifact

### Requirement: Event Log 0 SHALL persist baseline owner attestation material
The baseline record persisted for Event Log 0 SHALL include or reference the owner-attestation material needed for external verification of the declared chain owner public key.

#### Scenario: Baseline record carries owner bootstrap evidence
- **WHEN** TruCon persists Event Log 0
- **THEN** the persisted baseline contract SHALL include enough owner-attestation metadata for a verifier to reconstruct and validate the TEE-backed owner-key declaration

#### Scenario: Missing owner-attestation material rejects owner bootstrap
- **WHEN** a baseline initialization attempt declares a chain owner public key but does not provide the required owner-attestation material
- **THEN** the system SHALL reject the baseline initialization attempt rather than silently persisting an unauthenticated owner key

### Requirement: Event Log 0 uses the same signed predecessor contract as later records
Event Log 0 SHALL carry explicit signed predecessor fields using the reservation-backed replay contract rather than a special unsigned insertion path.

#### Scenario: Baseline payload uses null predecessor contract
- **WHEN** tc_api signs Event Log 0 for a newly created chain
- **THEN** the signed payload SHALL include `sequence_num=1`, `prev_event_digest=null`, and `prev_lookup_hash=null`

### Requirement: Non-blocking initialization
Subsequent `POST /commit` calls SHALL NOT be blocked while Event Log 0 is still in PENDING state. The submit daemon's ordered-submission behavior (ascending `sequence_num`) SHALL guarantee that Event Log 0 is published to the immutable backend before any subsequent records.

#### Scenario: Commit while baseline pending
- **WHEN** tc_api calls `POST /commit` after `POST /init-chain` but before Event Log 0 is confirmed
- **THEN** the commit succeeds normally, the new record gets `sequence_num=2` (or higher), and the submit daemon publishes Event Log 0 first

#### Scenario: Baseline terminal failure blocks chain
- **WHEN** Event Log 0 reaches `FAILED_TERMINAL` status in the submit daemon
- **THEN** all subsequent records in the same chain are blocked from submission (existing FAILED-blocks-successors behavior)

### Requirement: RTMR index correction
All RTMR extend and read operations SHALL use index `2` (the OS/application-layer register). The hardcoded `index=0` in the TruCon commit path SHALL be corrected to `index=2`.

#### Scenario: Commit extends RTMR[2]
- **WHEN** TruCon processes a `POST /commit` request with TDX hardware available
- **THEN** `_local_mr.extend(2, event_digest)` is called (not index 0)

#### Scenario: Baseline reads RTMR[2]
- **WHEN** TruCon processes `GET /init-chain/{chain_id}/baseline` with TDX hardware available
- **THEN** `_local_mr.read(2)` is called to capture the current measurement value

### Requirement: tc_api lifespan chain initialization
tc_api SHALL call `init_chain()` during its `lifespan()` startup for the `"default"` chain. If the chain already exists (HTTP 409), the initialization SHALL be silently skipped. If TruCon is unreachable, a warning SHALL be logged and tc_api SHALL continue starting.

#### Scenario: First worker initializes chain
- **WHEN** the first tc_api worker starts and no default chain exists
- **THEN** `init_chain("default")` succeeds, Event Log 0 is created

#### Scenario: Subsequent workers skip initialization
- **WHEN** a second tc_api worker starts and the default chain already exists
- **THEN** `init_chain("default")` receives HTTP 409 and skips without error

#### Scenario: TruCon unreachable at startup
- **WHEN** tc_api starts but TruCon is not yet available
- **THEN** tc_api logs a warning and continues; chain initialization can be retried on first request

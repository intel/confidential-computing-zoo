## MODIFIED Requirements

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

## ADDED Requirements

### Requirement: Event Log 0 SHALL persist baseline owner attestation material
The baseline record persisted for Event Log 0 SHALL include or reference the owner-attestation material needed for external verification of the declared chain owner public key.

#### Scenario: Baseline record carries owner bootstrap evidence
- **WHEN** TruCon persists Event Log 0
- **THEN** the persisted baseline contract SHALL include enough owner-attestation metadata for a verifier to reconstruct and validate the TEE-backed owner-key declaration

#### Scenario: Missing owner-attestation material rejects owner bootstrap
- **WHEN** a baseline initialization attempt declares a chain owner public key but does not provide the required owner-attestation material
- **THEN** the system SHALL reject the baseline initialization attempt rather than silently persisting an unauthenticated owner key
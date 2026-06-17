## MODIFIED Requirements

### Requirement: New non-default chains bootstrap baseline before first business event
The system SHALL NOT bootstrap Event Log 0 for previously unseen non-`default` chains. The only supported measured-chain bootstrap is the `default` chain. Any attempt to create or advance a new non-default measured chain SHALL be rejected before a business or runtime event is persisted.

#### Scenario: Default chain bootstraps baseline
- **WHEN** a producer initializes the measured chain for a fresh node epoch
- **THEN** the system SHALL complete baseline snapshot, baseline reservation, Event Log 0 signing, and `POST /init-chain` for `chain_id="default"` before replayable measured events are accepted

#### Scenario: First non-default commit is rejected
- **WHEN** a producer emits the first replayable event for a previously unseen non-`default` chain
- **THEN** the system SHALL reject the request and SHALL NOT create Event Log 0 for that non-default chain

### Requirement: Baseline snapshot endpoint
TruCon SHALL expose `GET /init-chain/{chain_id}/baseline` only for the `default` measured chain. The endpoint SHALL read the current RTMR[2] value (without extending it), compute the SHA-384 digest of the raw CCEL binary, and return `{rtmr_value, ccel_digest, init_token}` for `chain_id="default"`. Requests for any other chain ID SHALL fail.

#### Scenario: Successful default baseline snapshot
- **WHEN** tc_api calls `GET /init-chain/default/baseline` for a node epoch that does not yet have a default chain
- **THEN** TruCon reads RTMR[2], computes CCEL digest, generates an opaque `init_token`, and returns `{rtmr_value, ccel_digest, init_token}` with HTTP 200

#### Scenario: Non-default baseline request rejected
- **WHEN** tc_api calls `GET /init-chain/workload-a/baseline`
- **THEN** TruCon returns an explicit error indicating that only the default measured chain may be initialized

#### Scenario: Default chain already exists
- **WHEN** tc_api calls `GET /init-chain/default/baseline` for a chain that already has a `chain_state` entry
- **THEN** TruCon returns HTTP 409 with a descriptive error body

### Requirement: Chain initialization endpoint
TruCon SHALL expose `POST /init-chain` accepting `{chain_id, init_token, intent_token, signed_bundle, pub_key}` only for `chain_id="default"`. It SHALL verify the `init_token` is valid, SHALL verify that the supplied `intent_token` resolves to a valid baseline reservation for `default`, SHALL validate that the signed baseline bundle matches the reserved predecessor contract, SHALL persist Event Log 0 owner-attestation material sufficient to prove that `pub_key` was declared by the approved baseline initialization context, and SHALL then insert the baseline record with `sequence_num=1` and initialize `chain_state`. The RTMR SHALL NOT be extended for this record.

#### Scenario: Successful default chain initialization
- **WHEN** tc_api calls `POST /init-chain` with `chain_id="default"`, a valid `init_token`, a valid baseline `intent_token`, and a signed DSSE bundle whose predecessor fields match the reserved baseline contract
- **THEN** TruCon SHALL insert Event Log 0 into `commit_queue` with `sequence_num=1`, SHALL initialize `chain_state` for `default`, SHALL persist the owner-attestation material associated with the declared `pub_key`, SHALL mark the baseline intent consumed, and SHALL return `{record_id, sequence_num}` with HTTP 200

#### Scenario: Non-default initialization rejected
- **WHEN** tc_api calls `POST /init-chain` with `chain_id="workload-a"`
- **THEN** TruCon SHALL return an explicit error and SHALL NOT initialize that chain


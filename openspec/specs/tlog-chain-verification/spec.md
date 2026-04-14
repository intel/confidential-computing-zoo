## ADDED Requirements

### Requirement: chain_id in DSSE predicate subject
The DSSE envelope's In-Toto subject name SHALL include the `chain_id` in the format `trusted-log-chain_{chain_id}`. This enables Rekor search by subject name.

#### Scenario: DSSE subject contains chain_id
- **WHEN** tc_api constructs a DSSE statement for signing
- **THEN** the subject name SHALL be `trusted-log-chain_{chain_id}` where `chain_id` is the chain identifier from the commit request

### Requirement: Rekor search by chain_id and signer identity
Verification SHALL query Rekor for log entries matching the DSSE subject name (`trusted-log-chain_{chain_id}`) and filter results by the Trust API's signer identity (Fulcio certificate identity). Entries not signed by the expected identity SHALL be discarded.

#### Scenario: Retrieve chain entries from Rekor
- **WHEN** a verifier requests all entries for a given `chain_id`
- **THEN** the system SHALL query Rekor by subject name and return only entries whose Fulcio certificate identity matches the Trust API's workload identity

#### Scenario: Injected entries filtered out
- **WHEN** an attacker submits entries to Rekor with a matching subject name but a different signer identity
- **THEN** the verification flow SHALL discard those entries as they do not match the expected signer identity

### Requirement: RTMR ordering proof
Verification SHALL cross-check the chain of RTMR values from a TDX attestation quote against the `mr_value` sequence stored in confirmed records. The RTMR hardware chain proves that entries were extended in the claimed order.

#### Scenario: Verify RTMR chain integrity
- **WHEN** a verifier has a TDX attestation quote and the sequence of `mr_value` entries from confirmed records
- **THEN** the verifier SHALL confirm that sequential RTMR extends produce the attested final register value

### Requirement: prev_log_id excluded from signed payload
The DSSE predicate SHALL NOT include `prev_log_id`. Ordering integrity is proven by the RTMR hardware chain, not by signed fields.

#### Scenario: DSSE predicate does not contain prev_log_id
- **WHEN** tc_api builds the DSSE predicate for signing
- **THEN** the predicate payload SHALL NOT contain a `prev_log_id` field

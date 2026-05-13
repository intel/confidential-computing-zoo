## Purpose

Define the Event Log 0 owner bootstrap contract for single-owner chains, including the declared chain owner key, its baseline owner-attestation binding, and its separation from current-head attested evidence.

## Requirements

### Requirement: Event Log 0 SHALL declare a single chain owner public key
The baseline contract SHALL define one owner public key for the chain at Event Log 0. That key SHALL represent the single long-term chain owner for all later replayable writes. The owner key MAY be used for two purposes: (1) signing `owner_authorization` fields (ECDSA P-384 + SHA-384) to prove chain ownership on each commit, and (2) signing DSSE envelopes (ECDSA P-384 + SHA-256) for delegation-authorized operations submitted to Rekor with the owner public key as verifier.

#### Scenario: Baseline owner key declared at chain origin
- **WHEN** a new chain is initialized through Event Log 0
- **THEN** the baseline payload SHALL include exactly one declared chain owner public key and SHALL treat that key as the sole chain-local writer authority

#### Scenario: Single-owner semantics are explicit
- **WHEN** a verifier or operator inspects the baseline owner contract
- **THEN** the contract SHALL not imply support for multiple simultaneous owners, delegated writers, or key rotation in this version

#### Scenario: Owner key used for DSSE envelope signing
- **WHEN** a delegation-authorized operation needs to be submitted to Rekor without a Fulcio certificate
- **THEN** the chain owner private key SHALL be used to sign the DSSE envelope with ECDSA P-384 + SHA-256, and the corresponding public key PEM SHALL be used as the Rekor entry verifier

### Requirement: Baseline owner attestation SHALL bind the declared owner key to TEE-backed initialization context
The system SHALL define a baseline owner attestation contract whose report-data binding covers the declared owner public key together with Event Log 0 initialization context. At minimum, the binding SHALL cover `chain_id`, baseline `sequence_num`, the baseline platform measurement context, and the declared owner public key.

#### Scenario: Owner key is part of quote-backed binding
- **WHEN** baseline owner attestation is produced for Event Log 0
- **THEN** the quote-backed binding SHALL cover the declared owner public key and SHALL allow a verifier to detect substitution of that key after attestation

#### Scenario: Binding remains digest-based rather than PEM-in-quote
- **WHEN** the system encodes baseline owner attestation into quote-backed report data
- **THEN** it SHALL bind a canonical digest over the required fields rather than requiring the full PEM-form public key to be embedded verbatim as the trust-critical report-data payload

### Requirement: Baseline owner attestation SHALL remain separate from current-head attested evidence
The baseline owner attestation contract SHALL be distinct from the current-head attested evidence envelope and SHALL NOT redefine attested-head evidence as the source of truth for Event Log 0 owner bootstrap.

#### Scenario: Current-head evidence omits owner bootstrap contract
- **WHEN** a validator processes current-head attested evidence
- **THEN** the absence of baseline owner-attestation fields SHALL NOT invalidate that evidence package because owner bootstrap belongs to the baseline replay contract

#### Scenario: Verifier obtains owner bootstrap from Event Log 0 replay
- **WHEN** a verifier needs to establish which owner key governs a chain
- **THEN** it SHALL derive that fact from Event Log 0 replay and baseline owner attestation rather than from duplicated fields inside current-head attested evidence
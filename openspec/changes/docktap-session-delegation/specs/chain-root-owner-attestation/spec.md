## MODIFIED Requirements

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

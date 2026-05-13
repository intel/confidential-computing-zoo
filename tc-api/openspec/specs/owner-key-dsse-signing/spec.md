## Purpose

Define how the system signs DSSE envelopes and constructs Rekor entries using the chain owner key when operating under a session delegation (no OIDC token available).

## Requirements

### Requirement: DSSE envelope signing with owner key
The system SHALL sign DSSE envelopes using the chain owner key (EC P-384) with ECDSA + SHA-256 hash algorithm. The Pre-Authentication Encoding (PAE) SHALL follow the DSSE specification: `DSSEv1 {len(payloadType)} {payloadType} {len(payload)} {payload}`.

#### Scenario: Owner key signs DSSE envelope
- **WHEN** a delegation is active and no OIDC token is available
- **THEN** the system SHALL sign the DSSE envelope using the chain owner private key with ECDSA P-384 + SHA-256

#### Scenario: PAE format is correct
- **WHEN** a DSSE envelope is signed with the owner key
- **THEN** the signed data SHALL be the PAE-encoded bytes per the DSSE specification

### Requirement: Intoto proposed entry construction with raw public key
The system SHALL construct `intoto` v0.0.2 proposed entries for Rekor submission with the owner public key PEM as the `publicKey` field in each signature entry (not a Fulcio certificate).

#### Scenario: Intoto entry uses raw public key
- **WHEN** an owner-key-signed DSSE envelope is submitted to Rekor
- **THEN** the proposed entry SHALL be of type `intoto` with `apiVersion: "0.0.2"` and `signatures[].publicKey` set to base64-encoded owner public key PEM

#### Scenario: Payload double-base64 encoding
- **WHEN** an intoto proposed entry is constructed
- **THEN** the `envelope.payload` field SHALL be double-base64-encoded (base64 of the already-base64-encoded statement) per intoto v0.0.2 format

### Requirement: Rekor submission of owner-key-signed entries
The system SHALL submit owner-key-signed intoto entries to Rekor via HTTP POST to `/api/v1/log/entries`. The submission SHALL succeed and return a `uuid`, `log_index`, and `inclusion_proof`.

#### Scenario: Successful Rekor submission with raw public key
- **WHEN** an owner-key-signed intoto entry is POSTed to Rekor
- **THEN** Rekor SHALL return HTTP 201 with a valid UUID and log index

#### Scenario: Attestation storage persists payload
- **WHEN** an intoto entry is submitted to Rekor
- **THEN** the original In-Toto Statement SHALL be retrievable via the `attestation.data` field of the Rekor entry

### Requirement: Signing path selection in submit_operation
The system SHALL select the signing path based on available credentials: (1) if a valid OIDC token exists, use Fulcio signing (current behavior); (2) if no OIDC token but a valid delegation exists, use owner key signing.

#### Scenario: Fulcio path when OIDC token available
- **WHEN** a valid OIDC token is available and a delegation also exists
- **THEN** the system SHALL prefer the Fulcio signing path

#### Scenario: Owner key path when only delegation available
- **WHEN** no OIDC token is available but a valid delegation exists for the target chain
- **THEN** the system SHALL use the owner key signing path with delegation_id in the predicate

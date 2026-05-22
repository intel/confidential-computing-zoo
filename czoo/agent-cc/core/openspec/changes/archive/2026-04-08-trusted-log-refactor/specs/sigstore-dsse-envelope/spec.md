## ADDED Requirements

### Requirement: DSSE In-Toto Serialization
The system SHALL organize all metadata within the `EventLog` inside an In-Toto Statement json block, wrapped in a DSSE envelope format.

#### Scenario: `commit_record()` payload generation
- **WHEN** building the canonical json data
- **THEN** the system generates an In-Toto schema with predicateType `https://trusted-log.dev/v1`

### Requirement: Synchronous Fulcio Signing
The `commit_record()` API MUST trade its ephemeral OIDC token for a Fulcio Certificate strictly in the synchronous main-thread phase. 

#### Scenario: Missing / Expired Session Token
- **WHEN** the caller invoking `commit_record()` lacks a valid OIDC token
- **THEN** the API fast-fails before creating any DSSE Envelope or SQLite records

### Requirement: Verifier Integration
The system's `verify_record()` capability MUST correctly parse In-Toto statements and DSSE envelopes from the Rekor API response.

#### Scenario: Remote Replay
- **WHEN** a Verification client points at a `log_id`
- **THEN** the Verifier parses the `EventLog` payload successfully out of the DSSE envelope and matches its hash and signature against local logic

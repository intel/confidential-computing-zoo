# openviking-evidence-surface Specification

## Purpose
TBD - created by archiving change openviking-minimal-trusted-context-gate. Update Purpose after archive.
## Requirements
### Requirement: OpenViking exposes dedicated evidence and posture surfaces
The system SHALL define a dedicated evidence surface for trust verification and a separate posture surface for non-evidence runtime posture.

#### Scenario: Evidence surface is distinct from posture surface
- **WHEN** an implementation exposes trust-verification data for OpenClaw
- **THEN** it provides a dedicated evidence endpoint that is not the same contract as a readiness, health, or posture endpoint

#### Scenario: Posture surface remains separate
- **WHEN** an implementation exposes runtime posture information
- **THEN** it may provide posture data separately without requiring posture responses to stand in for attested evidence

### Requirement: Evidence responses contain the minimum trust claims
The system SHALL require evidence responses to contain the minimum claims needed for a fail-closed context-send decision.

#### Scenario: Required claims are present
- **WHEN** a local verify skill fetches evidence from OpenViking
- **THEN** the response includes `service_instance_id`, `tee_type`, `measurement` or `measurement_ref`, `ledger_head_id`, `generated_at`, `expires_at`, `policy_id`, and `policy_version`

#### Scenario: Missing required claims causes denial
- **WHEN** any required claim for context-send verification is missing or empty
- **THEN** the local verify skill must deny context transfer

### Requirement: Evidence responses support freshness and attested-head compatibility
The system SHALL define evidence freshness bounds and compatibility with the repository's attested-head evidence model.

#### Scenario: Evidence freshness is explicit
- **WHEN** OpenViking returns evidence for a context-send decision
- **THEN** the response includes generation time and expiration time so freshness can be evaluated deterministically

#### Scenario: Verification is compatibility-based
- **WHEN** the local verify skill validates OpenViking evidence using repository trust tooling
- **THEN** the contract requires compatibility with `tc-verify` and attested-head evidence semantics without requiring a specific runtime packaging choice

### Requirement: Evidence responses remain plaintext-free
The system SHALL keep evidence responses free of session, archive, and memory plaintext.

#### Scenario: Evidence does not contain memory data
- **WHEN** OpenViking returns evidence or posture data for verification
- **THEN** the response does not contain prompt text, context text, archive plaintext, privacy-restored values, or raw memory values


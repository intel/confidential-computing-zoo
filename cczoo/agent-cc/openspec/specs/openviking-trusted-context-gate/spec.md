# openviking-trusted-context-gate Specification

## Purpose
TBD - created by archiving change openviking-minimal-trusted-context-gate. Update Purpose after archive.
## Requirements
### Requirement: OpenClaw verifies OpenViking before context transfer
The system SHALL require OpenClaw to invoke a local verify skill before sending context to OpenViking.

#### Scenario: Context send allowed after successful verification
- **WHEN** OpenClaw prepares to send context and the local verify skill successfully validates the required OpenViking evidence and policy claims
- **THEN** the trust gate returns `allow` and OpenClaw may send context to OpenViking

#### Scenario: Context send denied when verification fails
- **WHEN** OpenClaw prepares to send context and the local verify skill cannot fetch, validate, or accept the required OpenViking evidence
- **THEN** the trust gate returns `deny` and OpenClaw does not send context to OpenViking

### Requirement: Context-send verification uses a five-minute trust cache
The system SHALL allow successful context-send verification results to be reused for at most five minutes when the cached result still matches the expected target and policy context.

#### Scenario: Trust result reused within TTL
- **WHEN** a prior successful verification result is less than five minutes old and its cache key still matches the current target URL, service instance, measurement, ledger head, and policy version
- **THEN** OpenClaw may reuse the cached `allow` result without performing a full verification round-trip

#### Scenario: Re-verification required after expiry or key mismatch
- **WHEN** the cached verification result is older than five minutes or any cache-key field no longer matches
- **THEN** OpenClaw must fetch and verify fresh evidence before sending context

### Requirement: Deny blocks context transfer without degradation
The system SHALL treat `deny` as a hard block for context transfer rather than a trigger for degraded or partial context sending.

#### Scenario: No degraded context send on deny
- **WHEN** the verify skill returns `deny` for a context-send attempt
- **THEN** OpenClaw must not send partial context, summary-only context, or plaintext fallback context to OpenViking

### Requirement: Context-send decisions are recorded as metadata only
The system SHALL support a minimal metadata-only decision record for `context_send.allow` and `context_send.deny` outcomes.

#### Scenario: Allow decision record excludes plaintext
- **WHEN** a context-send attempt is allowed
- **THEN** the decision record may include operation, result, policy identifier, evidence digest, subject hash, scope hash, and expiration metadata but must not include prompt or context plaintext

#### Scenario: Deny decision record excludes plaintext
- **WHEN** a context-send attempt is denied
- **THEN** the decision record may include denial reason and verification metadata but must not include prompt or context plaintext


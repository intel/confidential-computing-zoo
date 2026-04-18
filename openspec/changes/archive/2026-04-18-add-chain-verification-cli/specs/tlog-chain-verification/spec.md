## ADDED Requirements

### Requirement: Structured immutable-backend verification details
`TrustedLogAPI.verify_record()` SHALL return structured immutable-backend verification details that can be consumed by operator tooling.

#### Scenario: Verification result includes per-entry details
- **WHEN** immutable-backend replay verification finds one or more entries for the requested chain
- **THEN** the verification result SHALL include per-entry detail for each replayed immutable-backend record rather than only aggregate success metadata

#### Scenario: Verification result preserves source-specific failures
- **WHEN** immutable-backend replay verification encounters a digest mismatch, signer mismatch, traversal failure, or missing entries
- **THEN** the verification result SHALL report those failures in structured form so callers can render them without re-parsing exception text

### Requirement: Immutable-backend verification policy inputs
`TrustedLogAPI.verify_record()` SHALL support policy inputs needed by operator verification tooling.

#### Scenario: Signer identity constraint
- **WHEN** verification is invoked with a signer identity policy
- **THEN** immutable-backend replay verification SHALL filter or fail according to that identity constraint and SHALL report the applied identity in structured output

#### Scenario: Expected entry count constraint
- **WHEN** verification is invoked with an expected entry count policy
- **THEN** immutable-backend replay verification SHALL report the observed entry count in structured output so callers can enforce that policy deterministically

### Requirement: Immutable-backend verification remains distinct from RTMR verification
Immutable-backend replay verification SHALL continue to exclude RTMR ordering proof from its own responsibility.

#### Scenario: Caller requests immutable-backend verification
- **WHEN** `TrustedLogAPI.verify_record()` completes successfully
- **THEN** its result SHALL represent immutable-backend replay findings without claiming to perform RTMR ordering verification that belongs to TruCon local chain verification
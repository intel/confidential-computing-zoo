## ADDED Requirements

### Requirement: Immutable-backend verification proves accepted head entry inclusion
`TrustedLogAPI.verify_record()` SHALL require proof that the accepted Rekor-backed `head_log_id` was integrated into a signed Rekor tree state. Entry readback, payload decode, or replay continuity alone SHALL NOT be treated as sufficient proof of transparency-log inclusion for the accepted head entry.

#### Scenario: Accepted head entry is inclusion-verified
- **WHEN** immutable-backend verification accepts a Rekor-backed `head_log_id` and retrieves valid inclusion proof material for that entry
- **THEN** the verification result SHALL report that the accepted head entry was proven to belong to the corresponding signed Rekor tree state

#### Scenario: Entry readback without proof remains insufficient
- **WHEN** immutable-backend verification can read the accepted head entry body but cannot produce valid inclusion proof for that entry
- **THEN** the verification result SHALL NOT report the accepted head entry as log-inclusion-verified

### Requirement: Immutable-backend verification validates head checkpoint trust
`TrustedLogAPI.verify_record()` SHALL validate the signed checkpoint or equivalent signed tree head associated with the accepted head entry's inclusion proof before treating the accepted head entry as transparency-log verified.

#### Scenario: Checkpoint signature validation succeeds
- **WHEN** immutable-backend verification retrieves the checkpoint material associated with the accepted head entry's inclusion proof and the checkpoint signature validates against the configured trust source
- **THEN** the verification result SHALL report checkpoint trust as verified for that accepted head entry

#### Scenario: Checkpoint validation failure rejects head log verification
- **WHEN** immutable-backend verification retrieves checkpoint material for the accepted head entry but the checkpoint signature is invalid or does not chain to the configured trust source
- **THEN** the verification result SHALL report head log verification failure rather than degrading that result to successful inclusion

### Requirement: Immutable-backend verification reports explicit head log-verification states
`TrustedLogAPI.verify_record()` SHALL distinguish successful head-entry inclusion verification, degraded proof unavailability, and hard proof failure in structured output so callers can separate transparency-log assurance from replay continuity.

#### Scenario: Proof material unavailable yields degraded state
- **WHEN** immutable-backend verification establishes replay continuity for the accepted head entry but cannot retrieve enough inclusion proof or checkpoint material to complete head log verification
- **THEN** the verification result SHALL report the head log-verification dimension as degraded or incomplete rather than as successful

#### Scenario: Proof contradiction yields failed state
- **WHEN** immutable-backend verification detects that inclusion proof evaluation or checkpoint validation for the accepted head entry is cryptographically invalid
- **THEN** the verification result SHALL report the head log-verification dimension as failed

### Requirement: Immutable-backend verification supports explicit checkpoint bootstrap trust
`TrustedLogAPI.verify_record()` SHALL support an explicit initial trust source for validating the accepted head entry's checkpoint material when no previously trusted checkpoint is available.

#### Scenario: First trusted checkpoint uses bootstrap source
- **WHEN** immutable-backend verification runs without any previously trusted checkpoint state and a configured bootstrap trust source is available
- **THEN** the verifier SHALL use that bootstrap trust source to validate the accepted head entry's checkpoint material

#### Scenario: Bootstrap trust does not imply historical consistency proof
- **WHEN** immutable-backend verification succeeds for the accepted head entry using bootstrap checkpoint trust only
- **THEN** the result SHALL NOT claim that historical append-only consistency across time has been proven
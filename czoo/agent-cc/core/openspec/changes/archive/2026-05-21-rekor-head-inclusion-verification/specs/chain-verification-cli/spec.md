## ADDED Requirements

### Requirement: CLI reports head log verification separately from replay continuity
The chain verification CLI SHALL report accepted head-entry log inclusion and checkpoint trust as a verification dimension separate from immutable replay continuity, attested-head evidence validation, and troubleshooting-only data.

#### Scenario: JSON output separates head log verification fields
- **WHEN** the CLI produces JSON output for evidence-backed or troubleshooting verification
- **THEN** the normalized result SHALL preserve machine-readable fields for accepted head-entry inclusion status and checkpoint validation status in addition to replay and attested-head result sections

#### Scenario: Human-readable output separates head inclusion from replay success
- **WHEN** immutable replay succeeds but accepted head-entry log verification does not complete successfully
- **THEN** the default terminal output SHALL distinguish replay continuity from accepted head-entry transparency-log verification rather than collapsing them into one success statement

### Requirement: CLI preserves degraded and troubleshooting-only head log-verification states
The chain verification CLI SHALL preserve explicit degraded or troubleshooting-only states when accepted head-entry inclusion proof or checkpoint material is unavailable.

#### Scenario: Evidence-backed verification reports degraded head log verification
- **WHEN** evidence-backed verification establishes replay continuity for the accepted head but cannot complete accepted head-entry inclusion proof or checkpoint validation because required proof material is unavailable
- **THEN** the CLI SHALL report the log-verification dimension as degraded or incomplete rather than as verified

#### Scenario: Troubleshooting mode remains troubleshooting-only without proof material
- **WHEN** explicit live troubleshooting verification can read the accepted head entry but cannot complete accepted head-entry proof validation because required proof material is unavailable
- **THEN** the CLI SHALL identify that result as troubleshooting-only or internal diagnostics rather than as supported completed log verification

### Requirement: CLI treats invalid accepted head proof as a hard verification failure
The chain verification CLI SHALL treat cryptographically invalid accepted head-entry inclusion proof or checkpoint validation as a hard verification failure even when replay continuity succeeds.

#### Scenario: Invalid inclusion proof fails verification
- **WHEN** the CLI receives a verifier result showing that accepted head-entry inclusion proof evaluation failed
- **THEN** the CLI SHALL report verification failure rather than downgrading the result to degraded replay

#### Scenario: Invalid checkpoint signature fails verification
- **WHEN** the CLI receives a verifier result showing that accepted head-entry checkpoint validation failed
- **THEN** the CLI SHALL report verification failure and identify checkpoint trust as the failing dimension

### Requirement: CLI does not overstate bootstrap-trusted head verification
The chain verification CLI SHALL explain that accepted head-entry inclusion verified through bootstrap checkpoint trust proves the current head's transparency-log integration but does not prove cross-time consistency.

#### Scenario: JSON output preserves bootstrap-trust limitation
- **WHEN** the verifier completes accepted head-entry inclusion verification using an explicit bootstrap trust source for checkpoint validation
- **THEN** the CLI JSON output SHALL preserve machine-readable indication that the accepted head was verified with bootstrap trust and without historical consistency proof

#### Scenario: Human-readable output explains bootstrap scope
- **WHEN** the CLI produces terminal output for a run that used bootstrap checkpoint trust
- **THEN** the summary SHALL explain that the run proved accepted head-entry inclusion into a signed tree state but did not prove append-only consistency across time
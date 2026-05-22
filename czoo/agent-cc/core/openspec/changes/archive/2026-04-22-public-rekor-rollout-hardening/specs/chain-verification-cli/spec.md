## ADDED Requirements

### Requirement: CLI preserves replay rollout guidance
The chain verification CLI SHALL preserve machine-readable replay-boundary classifications in JSON output and SHALL render human-readable rollout guidance that distinguishes supported reservation-backed replay, degraded mixed-regime migration state, and invalid regression back to legacy linkage.

#### Scenario: JSON output preserves rollout boundary classification
- **WHEN** replay verification returns a machine-readable boundary classification for a mixed-regime chain
- **THEN** the CLI JSON output SHALL preserve that classification without replacing it with free-form summary text only

#### Scenario: Human-readable output explains degraded migration state
- **WHEN** replay verification reports a legacy-to-reservation boundary during staged rollout
- **THEN** the default terminal output SHALL identify the result as degraded migration state and SHALL explain that replay visibility exists but continuous reservation-backed predecessor proof is not available across the full history

#### Scenario: Human-readable output explains invalid regression
- **WHEN** replay verification reports a regression from reservation-backed replay into incompatible legacy linkage
- **THEN** the default terminal output SHALL identify that result as invalid regression rather than presenting it as a normal migration boundary or generic replay failure

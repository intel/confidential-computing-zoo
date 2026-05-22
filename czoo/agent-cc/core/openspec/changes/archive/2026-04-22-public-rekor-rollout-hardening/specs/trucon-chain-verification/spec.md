## ADDED Requirements

### Requirement: TruCon classifies replay rollout boundaries
`GET /verify-chain/{chain_id}` SHALL preserve rollout-boundary classifications for mixed legacy and reservation-backed replay regimes so operators can distinguish degraded migration state from invalid regression. These classifications SHALL remain machine-readable and SHALL be exposed independently from RTMR availability.

#### Scenario: Legacy boundary is reported as degraded migration state
- **WHEN** chain verification encounters a boundary from legacy predecessor linkage into the reservation-backed signed predecessor regime
- **THEN** the response SHALL preserve a machine-readable boundary classification for the affected entry or summary and SHALL identify that boundary as degraded migration state rather than as a generic predecessor mismatch

#### Scenario: Regression after reservation-backed entry is reported as invalid
- **WHEN** chain verification encounters a regression into incompatible legacy predecessor linkage after a chain has already produced reservation-backed replayable records
- **THEN** the response SHALL preserve a machine-readable boundary classification that marks the regression as invalid rather than as degraded migration state

#### Scenario: Boundary classification survives non-TEE verification
- **WHEN** TruCon verifies a chain in non-TEE mode and a replay-regime boundary is present
- **THEN** the response SHALL preserve the same machine-readable boundary classification even if `mr_ok` is unavailable or skipped for some entries

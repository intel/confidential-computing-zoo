## MODIFIED Requirements

### Requirement: Evidence-backed verification input mode
The CLI SHALL treat a valid v1 attested-head evidence package as the supported external operator input for verification and SHALL derive replay targets from that package.

#### Scenario: Verify from exported evidence
- **WHEN** an operator invokes the CLI with a valid v1 attested-head evidence package
- **THEN** the CLI SHALL derive `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from that package instead of requiring live TruCon discovery calls

#### Scenario: Invalid evidence package rejected
- **WHEN** an operator invokes the CLI with a package that fails the shared attested-head evidence validation rules
- **THEN** the CLI SHALL fail verification and SHALL report the evidence package as invalid before attempting immutable-backend replay

#### Scenario: External verification without evidence is rejected
- **WHEN** an operator invokes the CLI without an evidence package and without explicitly selecting troubleshooting mode
- **THEN** the CLI SHALL fail fast and SHALL instruct the caller to use exported evidence for supported external verification

### Requirement: Live TruCon mode is retained only as explicit troubleshooting mode
The CLI SHALL allow live TruCon-backed verification only when the caller explicitly selects a troubleshooting-oriented mode, and it SHALL not present that mode as a supported external verifier contract.

#### Scenario: Troubleshooting mode invocation is explicit
- **WHEN** an operator invokes the CLI with a live `chain_id` selector
- **THEN** the CLI SHALL require an explicit troubleshooting selector rather than silently treating the request as normal external verification

#### Scenario: Troubleshooting mode is labeled as internal
- **WHEN** the CLI runs in live TruCon-backed troubleshooting mode
- **THEN** help text, diagnostics, and final result reporting SHALL identify that run as troubleshooting or internal mode rather than as the preferred verifier contract

#### Scenario: Evidence-backed invocation avoids live TruCon dependency
- **WHEN** an operator invokes the CLI with an evidence package
- **THEN** the CLI SHALL complete without requiring successful live TruCon connectivity for chain-state discovery or local verification

### Requirement: `chain_id` is not a standalone external verification target in v1
The CLI SHALL accept a v1 attested-head evidence package as the supported external verification target in v1, and it MAY accept a `chain_id` only when troubleshooting mode is explicitly requested.

#### Scenario: Verify a chain by evidence package
- **WHEN** an operator invokes the CLI with a v1 attested-head evidence package
- **THEN** the CLI SHALL treat the package as the verification target source and SHALL NOT require any alternate selector to resolve the attested head

#### Scenario: Bare chain_id invocation is not treated as external verification
- **WHEN** an operator invokes the CLI with a `chain_id` but without explicit troubleshooting mode
- **THEN** the CLI SHALL reject the invocation instead of silently reinterpreting it as a supported external verifier path

### Requirement: Dual-source verification aggregation
The CLI SHALL treat immutable-backend replay and attested-head evidence validation as the supported external verification sources, while any live TruCon verification that remains available SHALL be surfaced only as explicitly requested troubleshooting data.

#### Scenario: Evidence-backed verification succeeds
- **WHEN** immutable-backend replay succeeds and the attested-head evidence package is valid and matches the replayed head
- **THEN** the CLI SHALL report successful replay and attested-head outcomes in the normalized result and SHALL render a successful overall summary without requiring live TruCon success

#### Scenario: Troubleshooting source is unavailable
- **WHEN** the CLI runs in explicit troubleshooting mode and the TruCon source is unavailable or errors
- **THEN** the CLI SHALL preserve that failed troubleshooting outcome in the normalized result while still identifying the mode as internal diagnostics rather than normal external verification
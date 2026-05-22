## ADDED Requirements

### Requirement: Evidence-backed verification input mode
The CLI SHALL support a primary verification mode that consumes a v1 attested-head evidence package and derives replay targets from that package.

#### Scenario: Verify from exported evidence
- **WHEN** an operator invokes the CLI with a valid v1 attested-head evidence package
- **THEN** the CLI SHALL derive `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from that package instead of requiring live TruCon discovery calls

#### Scenario: Invalid evidence package rejected
- **WHEN** an operator invokes the CLI with a package that fails the shared attested-head evidence validation rules
- **THEN** the CLI SHALL fail verification and SHALL report the evidence package as invalid before attempting immutable-backend replay

### Requirement: Replay must reach the attested head described by evidence
The CLI SHALL verify that immutable-backend replay reaches the same chain head described by the attested-head evidence package.

#### Scenario: Evidence head matches replayed head
- **WHEN** immutable-backend replay reaches a head whose `chain_id`, `sequence_num`, `head_log_id`, and `mr_value` match the attested-head evidence package
- **THEN** the CLI SHALL report the replay-to-evidence association as successful

#### Scenario: Evidence head does not match replayed head
- **WHEN** immutable-backend replay does not reach the `chain_id`, `sequence_num`, `head_log_id`, or `mr_value` described by the attested-head evidence package
- **THEN** the CLI SHALL fail verification and SHALL report which association field did not match

### Requirement: Live TruCon mode is retained only as transitional fallback
The CLI SHALL retain live TruCon-assisted verification as a transitional fallback mode rather than as the preferred verifier contract.

#### Scenario: Live fallback invocation
- **WHEN** an operator invokes the CLI without an evidence package and uses the live TruCon path
- **THEN** the CLI SHALL identify that run as fallback or transitional mode in help text, diagnostics, and final result reporting

#### Scenario: Evidence-backed invocation avoids live TruCon dependency
- **WHEN** an operator invokes the CLI with an evidence package
- **THEN** the CLI SHALL complete without requiring successful live TruCon connectivity for chain-state discovery or local verification

## MODIFIED Requirements

### Requirement: `chain_id` is the only v1 verification target
The CLI SHALL accept either a `chain_id` for transitional live fallback verification or a v1 attested-head evidence package for primary evidence-backed verification in v1.

#### Scenario: Verify a chain by chain_id in fallback mode
- **WHEN** an operator invokes the CLI with a `chain_id` and without an evidence package
- **THEN** the CLI SHALL verify exactly that chain in live fallback mode and SHALL NOT silently reinterpret the selector as evidence-backed verification

#### Scenario: Verify a chain by evidence package
- **WHEN** an operator invokes the CLI with a v1 attested-head evidence package
- **THEN** the CLI SHALL treat the package as the verification target source and SHALL NOT require any alternate selector to resolve the attested head

### Requirement: Dual-source verification aggregation
The CLI SHALL treat immutable-backend replay and attested-head evidence validation as the primary verification sources, with live TruCon verification retained only as an explicit fallback source.

#### Scenario: Evidence-backed verification succeeds
- **WHEN** immutable-backend replay succeeds and the attested-head evidence package is valid and matches the replayed head
- **THEN** the CLI SHALL report successful replay and attested-head outcomes in the normalized result and SHALL render a successful overall summary without requiring live TruCon success

#### Scenario: Fallback source is unavailable
- **WHEN** the CLI runs in live fallback mode and the TruCon source is unavailable or errors
- **THEN** the CLI SHALL preserve that failed fallback outcome in the normalized result and SHALL report the overall result according to the remaining available source data and requested policy flags

### Requirement: Stable JSON result model
The CLI SHALL support a stable JSON output mode that distinguishes immutable replay findings from attested-head evidence findings and from live fallback findings.

#### Scenario: JSON output requested
- **WHEN** the CLI is invoked with `--json`
- **THEN** the output SHALL include top-level sections for `target`, `mode`, `summary`, `replay`, `attested_head`, and `errors`, and it MAY include an additional fallback section when live TruCon verification is used

#### Scenario: JSON output includes per-record replay detail
- **WHEN** JSON output is produced for a chain with one or more replayed records
- **THEN** the replay portion of the normalized result SHALL include record-level identifiers and verification detail sufficient to diagnose immutable-backend failures independently from attested-head failures

### Requirement: Human-readable verification summary
The CLI SHALL produce a human-readable summary by default that clearly separates replay outcomes from attested-head or fallback outcomes.

#### Scenario: Default terminal output
- **WHEN** the CLI is invoked without `--json`
- **THEN** it SHALL print a concise summary that includes overall status, effective verification mode, replay outcome, attested-head outcome when applicable, and fallback status when applicable

#### Scenario: Pending or incomplete state displayed
- **WHEN** the verified chain contains records that are not yet confirmed in the immutable backend or evidence is unavailable for a pending-only chain
- **THEN** the human-readable output SHALL identify the verification as incomplete or ineligible for evidence-backed verification rather than omitting that state
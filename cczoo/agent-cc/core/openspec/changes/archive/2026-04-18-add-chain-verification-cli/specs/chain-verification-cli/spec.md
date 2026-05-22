## ADDED Requirements

### Requirement: Package verification CLI entry point
The system SHALL expose a package-level chain verification CLI command for operators and auditors.

#### Scenario: Console script is installed
- **WHEN** the package is installed in a supported environment
- **THEN** a console command for chain verification SHALL be available without invoking a repository-local helper script

#### Scenario: CLI uses package configuration
- **WHEN** the CLI starts verification
- **THEN** it SHALL use the package's configured runtime settings and shared verification code paths rather than maintaining an independent script-only configuration path

### Requirement: `chain_id` is the only v1 verification target
The CLI SHALL accept a `chain_id` as its sole verification target in v1.

#### Scenario: Verify a chain by chain_id
- **WHEN** an operator invokes the CLI with a `chain_id`
- **THEN** the CLI SHALL verify exactly that chain and SHALL NOT require any additional selector

#### Scenario: Unsupported alternate selector
- **WHEN** an operator attempts to use workload-, instance-, record-, or log-id-based targeting in v1
- **THEN** the CLI SHALL reject the invocation as unsupported rather than silently changing target semantics

### Requirement: Dual-source verification aggregation
The CLI SHALL aggregate immutable-backend replay verification and TruCon local chain verification into one normalized result.

#### Scenario: Both sources succeed
- **WHEN** immutable-backend replay verification succeeds and TruCon local chain verification succeeds for the requested chain
- **THEN** the CLI SHALL report both source outcomes in the normalized result and SHALL render a successful overall summary

#### Scenario: One source is unavailable
- **WHEN** one verification source is unavailable or errors during execution
- **THEN** the CLI SHALL preserve the failed source outcome in the normalized result and SHALL report the overall result according to the remaining source data and requested policy flags

### Requirement: Stable JSON result model
The CLI SHALL support a stable JSON output mode that is owned by the CLI contract rather than by any underlying source response shape.

#### Scenario: JSON output requested
- **WHEN** the CLI is invoked with `--json`
- **THEN** the output SHALL include top-level sections for `target`, `mode`, `summary`, `sources`, `entries`, and `errors`

#### Scenario: JSON output includes per-record detail
- **WHEN** JSON output is produced for a chain with one or more records
- **THEN** each normalized entry SHALL include record-level identifiers and verification detail sufficient to diagnose immutable-backend and local-chain failures

### Requirement: Human-readable verification summary
The CLI SHALL produce a human-readable summary by default.

#### Scenario: Default terminal output
- **WHEN** the CLI is invoked without `--json`
- **THEN** it SHALL print a concise summary that includes overall status, effective verification mode, source-level outcomes, and per-record verification detail

#### Scenario: Pending records displayed
- **WHEN** the verified chain contains records that are not yet confirmed in the immutable backend
- **THEN** the human-readable output SHALL identify those records as pending rather than omitting them from the result

### Requirement: Supported verification policy flags
The CLI SHALL support the flags `--signer-identity`, `--expected-entry-count`, `--fail-on-pending`, and `--require-tee`.

#### Scenario: Signer identity filter applied
- **WHEN** an operator passes `--signer-identity <value>`
- **THEN** immutable-backend replay verification SHALL apply that identity constraint and report whether matching verified entries remain

#### Scenario: Expected entry count mismatch
- **WHEN** an operator passes `--expected-entry-count <n>` and the normalized result contains a different number of verified entries
- **THEN** the CLI SHALL fail verification and SHALL report the mismatch in the summary and errors output

#### Scenario: Fail on pending enabled
- **WHEN** an operator passes `--fail-on-pending` and one or more records remain pending
- **THEN** the CLI SHALL return a failure result even if structural verification succeeded for the confirmed portion of the chain

#### Scenario: Require TEE enabled without TEE evidence
- **WHEN** an operator passes `--require-tee` and the chain can only be verified in non-TEE fallback mode
- **THEN** the CLI SHALL fail verification and SHALL report that TEE evidence was required but unavailable

### Requirement: Non-TEE results are test-only
The CLI SHALL classify non-TEE fallback verification as test-only behavior rather than production-equivalent TEE verification.

#### Scenario: Non-TEE fallback result
- **WHEN** TruCon reports that RTMR evidence is unavailable and verification proceeds via non-TEE fallback checks
- **THEN** the normalized result SHALL identify the effective verification mode as non-TEE fallback and SHALL mark it as test-only

#### Scenario: TEE result
- **WHEN** RTMR-backed verification is available
- **THEN** the normalized result SHALL identify the effective verification mode as TEE-backed verification
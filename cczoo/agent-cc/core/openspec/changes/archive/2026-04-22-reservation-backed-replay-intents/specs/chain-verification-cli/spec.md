## MODIFIED Requirements

### Requirement: Stable JSON result model
The CLI SHALL support a stable JSON output mode that distinguishes immutable replay findings from attested-head evidence findings and from live fallback findings. For reservation-backed replayable records, the replay result model SHALL expose signed predecessor-continuity findings rather than backend-specific `prev_log_id` linkage status.

#### Scenario: JSON output requested
- **WHEN** the CLI is invoked with `--json`
- **THEN** the output SHALL include top-level sections for `target`, `mode`, `summary`, `replay`, `attested_head`, and `errors`, and it MAY include an additional fallback section when live TruCon verification is used

#### Scenario: JSON output includes per-record replay detail
- **WHEN** JSON output is produced for a chain with one or more replayed records
- **THEN** the replay portion of the normalized result SHALL include record-level identifiers and verification detail sufficient to diagnose immutable-backend predecessor failures independently from attested-head failures

## ADDED Requirements

### Requirement: CLI reports signed predecessor continuity findings
The chain verification CLI SHALL render signed predecessor verification results in both JSON and human-readable output so operators can distinguish candidate-discovery failures from signed continuity mismatches.

#### Scenario: JSON output reports predecessor status
- **WHEN** a replayed record includes reservation-backed predecessor verification detail
- **THEN** the CLI JSON output SHALL expose `predecessor_ok` and any associated candidate-discovery diagnostics for that record

#### Scenario: Human-readable output reports predecessor failure source
- **WHEN** replay verification fails because predecessor lookup returned no matching signed candidate or because the signed predecessor contract mismatched
- **THEN** the default terminal output SHALL identify predecessor continuity as the failing replay dimension rather than reporting only a generic immutable-backend failure
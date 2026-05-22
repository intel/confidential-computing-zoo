## MODIFIED Requirements

### Requirement: Stable JSON result model
The CLI SHALL support a stable JSON output mode that distinguishes immutable replay findings from attested-head evidence findings and from live fallback findings. For reservation-backed replayable records, the replay result model SHALL expose signed predecessor-continuity findings rather than backend-specific `prev_log_id` linkage status, and SHALL preserve the machine-readable predecessor vocabulary emitted by immutable replay and TruCon verification.

#### Scenario: JSON output requested
- **WHEN** the CLI is invoked with `--json`
- **THEN** the output SHALL include top-level sections for `target`, `mode`, `summary`, `replay`, `attested_head`, and `errors`, and it MAY include an additional fallback section when live TruCon verification is used

#### Scenario: JSON output includes per-record replay detail
- **WHEN** JSON output is produced for a chain with one or more replayed records
- **THEN** the replay portion of the normalized result SHALL include record-level identifiers and verification detail sufficient to diagnose immutable-backend predecessor failures independently from attested-head failures

#### Scenario: JSON output preserves predecessor pipeline detail
- **WHEN** a replayed record includes reservation-backed predecessor verification detail
- **THEN** the CLI JSON output SHALL preserve `predecessor_ok`, `predecessor_status`, and any available candidate-pipeline counts rather than reducing them to text-only diagnostics

#### Scenario: JSON output preserves replay boundary classification
- **WHEN** replay verification encounters a boundary between predecessor-proof regimes
- **THEN** the JSON result SHALL preserve a machine-readable `boundary_status` or equivalent replay-regime classification rather than forcing operators to infer that state from free-form error text

### Requirement: CLI reports signed predecessor continuity findings
The chain verification CLI SHALL render signed predecessor verification results in both JSON and human-readable output so operators can distinguish candidate-discovery failures from signed continuity mismatches, decode failures from no-match outcomes, and degraded replay from invalid replay.

#### Scenario: JSON output reports predecessor status
- **WHEN** a replayed record includes reservation-backed predecessor verification detail
- **THEN** the CLI JSON output SHALL expose `predecessor_status` in addition to `predecessor_ok` and associated candidate-discovery diagnostics for that record

#### Scenario: Human-readable output reports predecessor failure source
- **WHEN** replay verification fails because predecessor lookup returned no matching signed candidate, because candidate discovery failed, because discovered candidates could not be decoded into replayable entries, or because more than one candidate matched the signed predecessor contract
- **THEN** the default terminal output SHALL identify predecessor continuity as the failing replay dimension and SHALL distinguish those failure modes rather than reporting only a generic immutable-backend failure

#### Scenario: Human-readable output distinguishes degraded replay from invalid replay
- **WHEN** replay verification encounters incomplete replay state, pending-only replay state, or a replay boundary between incompatible proof regimes
- **THEN** the CLI SHALL distinguish degraded verification from invalid replay rather than collapsing both into one hard-failure label
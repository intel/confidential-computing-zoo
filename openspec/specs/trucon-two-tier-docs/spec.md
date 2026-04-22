## Purpose

Define the documentation requirements for the repository's two-tier trusted-log architecture.

## Requirements

### Requirement: Two-tier architecture documentation model
The project SHALL maintain two tiers of architecture documentation: a top-level `docs/architecture.md` describing system-wide topology and inter-service contracts, and `docs/trusted-log/architecture.md` describing the TruCon and trusted-log module implementation details.

#### Scenario: Top-level doc describes system topology
- **WHEN** a reader opens the top-level `docs/architecture.md`
- **THEN** they SHALL find the REST API + Docktap + TruCon service topology, inter-service contracts, deployment model, and migration plan

#### Scenario: Trusted-log doc describes implementation detail
- **WHEN** a reader opens `docs/trusted-log/architecture.md`
- **THEN** they SHALL find TruCon internal architecture including sequencer lock, SQLite schema, crash recovery, DSSE signing, embedded daemon, and verification model

### Requirement: One-way dependency direction
The `docs/trusted-log/` documentation directory SHALL be self-contained with no references to the top-level `docs/architecture.md`. The top-level `docs/architecture.md` MAY reference `docs/trusted-log/` documents for implementation detail.

#### Scenario: Trusted-log docs have no upward references
- **WHEN** any file in `docs/trusted-log/` is inspected
- **THEN** it SHALL NOT contain links or references to the top-level `docs/architecture.md`

#### Scenario: Top-level doc references trusted-log for detail
- **WHEN** the top-level `docs/architecture.md` describes TruCon implementation
- **THEN** it SHALL reference `docs/trusted-log/architecture.md` for internal details rather than duplicating them

### Requirement: Planned capabilities marked explicitly
Capabilities described in the top-level `docs/architecture.md` that are not yet implemented SHALL be annotated with a "Status: Planned" label.

#### Scenario: Docktap integration marked as planned
- **WHEN** a reader views the Docktap Service section in top-level `docs/architecture.md`
- **THEN** it SHALL include a "Status: Planned — not yet implemented" annotation

#### Scenario: Instance mapping marked as planned
- **WHEN** a reader views the instance mapping section in top-level `docs/architecture.md`
- **THEN** it SHALL include a "Status: Planned — not yet implemented" annotation

### Requirement: prev_log_id chaining documented as future method
The `docs/trusted-log/architecture.md` SHALL document prev_log_id-based chain linkage as a future secondary ordering method. The current default ordering method (RTMR hardware measurement chain) SHALL remain unchanged.

#### Scenario: Future ordering method documented
- **WHEN** a reader views the chain ordering section in `docs/trusted-log/architecture.md`
- **THEN** they SHALL find a description of prev_log_id chaining as a planned alternative for non-TEE environments, alongside the current RTMR-based ordering as the default

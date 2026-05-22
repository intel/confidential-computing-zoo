## ADDED Requirements

### Requirement: TruCon SHALL maintain workload-to-instance mapping records
TruCon SHALL persist mapping relationships between workload identifiers and runtime Docker instance identifiers to support audit and verification workflows.

#### Scenario: Register instance mapping for launched workload
- **WHEN** a caller reports that a workload launch produced one or more Docker instances
- **THEN** TruCon stores mapping entries that relate workload identity to each instance identity

#### Scenario: Update instance mapping on lifecycle change
- **WHEN** a caller reports instance lifecycle changes such as restart, replacement, or termination
- **THEN** TruCon updates mapping state while preserving historical mapping lineage for audit purposes

### Requirement: TruCon SHALL support instance-centric and workload-centric mapping queries
TruCon SHALL provide query interfaces that resolve workload to instances and instances to associated trusted events.

#### Scenario: Query instances for workload
- **WHEN** a caller queries by workload identifier
- **THEN** TruCon returns mapped instance identifiers and their current mapping state

#### Scenario: Query event correlations for instance
- **WHEN** a caller queries by instance identifier
- **THEN** TruCon returns associated trusted event references and relevant mapping metadata

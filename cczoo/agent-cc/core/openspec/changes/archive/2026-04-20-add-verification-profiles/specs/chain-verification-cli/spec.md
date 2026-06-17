## ADDED Requirements

### Requirement: CLI reports profile-scoped verification verdicts
The chain verification CLI SHALL evaluate and report profile-scoped verdicts for `build`, `publish`, `launch`, and `docktap-runtime` separately from structural replay and evidence results.

#### Scenario: Profile verdicts included in JSON output
- **WHEN** an operator invokes the CLI with `--json`
- **THEN** the normalized result SHALL include a dedicated profile-verdict section that reports the verdict, matched evidence set, and profile-specific findings for each evaluated profile

#### Scenario: Profile verdicts separated from replay status
- **WHEN** immutable-backend replay succeeds but one or more profiles fail their application-layer checks
- **THEN** the CLI SHALL preserve replay success while reporting the failing profiles independently rather than collapsing everything into one undifferentiated status

### Requirement: CLI evaluates the latest launch attempt by `launch_id`
The chain verification CLI SHALL evaluate the launch profile against the latest workload-scoped launch attempt identified by `launch_id`.

#### Scenario: Latest launch_id selected
- **WHEN** the workload chain contains more than one launch-related event set
- **THEN** the CLI SHALL determine the latest `launch_id` present in the workload chain and SHALL restrict launch-profile evaluation to the event set attributed to that identifier

#### Scenario: Pre-create launch failure remains attributable
- **WHEN** the latest launch attempt fails before a container instance is created
- **THEN** the CLI SHALL still evaluate and report that launch attempt by `launch_id` rather than skipping launch verification due to missing `instance_id`

### Requirement: CLI distinguishes hard failures, warnings, and incomplete profile evidence
The chain verification CLI SHALL distinguish profile hard failures, warning-only omissions, and incomplete evidence in both text and JSON output.

#### Scenario: Warning profile result
- **WHEN** a profile satisfies all hard requirements but omits warning-only metadata
- **THEN** the CLI SHALL report that profile as `warning` and SHALL enumerate the warning findings separately from hard failures

#### Scenario: Incomplete profile result
- **WHEN** a profile cannot be fully evaluated because the event set is pending, truncated, or otherwise incomplete
- **THEN** the CLI SHALL report that profile as `incomplete` and SHALL identify which required evidence was missing
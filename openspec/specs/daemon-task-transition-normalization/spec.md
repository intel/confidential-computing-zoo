# daemon-task-transition-normalization Specification

## Purpose
TBD - created by archiving change docktap-containerd-task-normalization. Update Purpose after archive.

## Requirements
### Requirement: Containerd task transitions SHALL use a documented normalized observation contract
Docktap documentation SHALL define normalized task-transition observations for daemon/internal mixed-trace analysis so containerd task activity is not left as raw free-text examples.

#### Scenario: Task transitions are documented as normalized observations
- **WHEN** Docktap documentation explains daemon/internal `task lifecycle` activity
- **THEN** it SHALL describe the relevant containerd task transitions as normalized observations rather than only as ad hoc narrative trace commentary

#### Scenario: Normalized task transitions remain within the daemon/internal plane
- **WHEN** the normalized task-transition contract is documented
- **THEN** it SHALL treat those observations as daemon/internal-plane facts rather than as HTTP API request classes

### Requirement: The first normalized contract SHALL define a minimum task-transition set
Docktap documentation SHALL define at least `tasks/create`, `tasks/start`, `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` as the first normalized containerd task-transition set.

#### Scenario: Container task transitions are included
- **WHEN** the first normalized task-transition contract is documented
- **THEN** it SHALL include `tasks/create` and `tasks/start`

#### Scenario: Exec task transitions are included
- **WHEN** the first normalized task-transition contract is documented
- **THEN** it SHALL include `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`

### Requirement: Normalized task transitions SHALL define minimum canonical daemon/internal facts
Docktap documentation SHALL define the minimum canonical facts used to describe normalized task transitions, including topic, timestamp, source namespace, container identity, and exec identity when available.

#### Scenario: Canonical daemon/internal facts are documented
- **WHEN** a normalized task transition is described in documentation
- **THEN** the documentation SHALL identify the minimum canonical daemon/internal facts needed to describe that transition

#### Scenario: Missing exec identity remains representable
- **WHEN** an exec-related task transition does not expose a reliable exec identifier in the immediate trace evidence
- **THEN** the documentation SHALL allow exec identity to remain unavailable without treating the transition itself as invalid

### Requirement: Container-task and exec-task transitions SHALL remain distinguishable inside one task-lifecycle family
Docktap documentation SHALL distinguish container-task transitions from exec-task transitions while keeping both inside the existing daemon/internal `task lifecycle` phase family.

#### Scenario: Container task transitions are not conflated with exec transitions
- **WHEN** `tasks/create` and `tasks/start` are documented
- **THEN** they SHALL be described as container-task transitions rather than as exec-task transitions

#### Scenario: Exec task transitions remain inside task lifecycle
- **WHEN** `tasks/exec-added`, `tasks/exec-started`, or `tasks/exit` are documented
- **THEN** they SHALL remain part of the daemon/internal `task lifecycle` family rather than being promoted to a separate top-level family

### Requirement: Required cold-start transitions and supplemental transitions SHALL remain explicit
Docktap documentation SHALL state which normalized task transitions are required for cold-start interpretation and which remain supplemental for richer runtime analysis.

#### Scenario: Cold-start-required transitions are defined
- **WHEN** the documentation describes minimum mixed-trace interpretation for container cold start
- **THEN** it SHALL identify `tasks/create` and `tasks/start` as the required normalized task transitions

#### Scenario: Supplemental runtime transitions are defined
- **WHEN** the documentation describes richer runtime analysis beyond cold start
- **THEN** it SHALL identify exec-related transitions as supplemental rather than required for minimal cold-start interpretation

### Requirement: Cross-plane joins and higher-level interpretation SHALL remain deferred
Docktap documentation SHALL state that normalized task-transition observations do not by themselves define API/internal correlation rules, healthcheck interpretation, attach-stream semantics, or parser implementation.

#### Scenario: API/internal correlation remains deferred
- **WHEN** the normalized task-transition contract is documented
- **THEN** it SHALL state that API-path to daemon/internal correlation remains future work

#### Scenario: Healthcheck and parser concerns remain deferred
- **WHEN** the normalized task-transition contract references exec activity or mixed-trace collection
- **THEN** it SHALL state that healthcheck-vs-foreground interpretation, attach-stream modeling, and parser or ingestion implementation remain future work

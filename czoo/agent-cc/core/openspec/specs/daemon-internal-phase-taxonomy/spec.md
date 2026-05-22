# daemon-internal-phase-taxonomy Specification

## Purpose
TBD - created by archiving change docktap-daemon-phase-taxonomy. Update Purpose after archive.
## Requirements
### Requirement: Daemon-internal phases SHALL use a documented taxonomy distinct from API-path observations
Docktap documentation SHALL define daemon/runtime-internal phases as a separate observation layer from HTTP API request classification so mixed traces can describe both planes without collapsing them into one model.

#### Scenario: Internal phase taxonomy is separated from request classification
- **WHEN** Docktap documentation explains mixed Docker traces
- **THEN** it SHALL describe daemon/runtime-internal phases as distinct from HTTP API request classes

#### Scenario: Internal phase taxonomy complements existing request observations
- **WHEN** the documentation references both proxy-observed requests and daemon/internal activity
- **THEN** it SHALL state that the internal taxonomy complements rather than replaces the API-path observation model

### Requirement: The initial taxonomy SHALL define five stable top-level phase families
Docktap documentation SHALL define at least storage/mount, runtime-spec/bundle, task lifecycle, attach/stream, and housekeeping as the first stable daemon/runtime-internal phase families.

#### Scenario: Storage and runtime preparation families are documented
- **WHEN** the taxonomy describes daemon/internal phases before workload runtime starts
- **THEN** it SHALL include stable families for storage/mount activity and runtime-spec/bundle preparation

#### Scenario: Runtime execution and maintenance families are documented
- **WHEN** the taxonomy describes daemon/internal phases during and after workload runtime activity
- **THEN** it SHALL include stable families for task lifecycle, attach/stream activity, and housekeeping work

### Requirement: Example mappings SHALL ground the taxonomy in real mixed traces
Docktap documentation SHALL use representative daemon log examples to illustrate how the documented phase families map onto mixed Docker traces.

#### Scenario: OpenClaw daemon analysis provides representative mappings
- **WHEN** the taxonomy is introduced in documentation
- **THEN** it SHALL map representative lines from `openclaw-docker-analysis.md` into the documented phase families

#### Scenario: Each family has at least one concrete example
- **WHEN** a top-level daemon/internal phase family is documented
- **THEN** the documentation SHALL include at least one concrete example of a trace line or trace segment that fits that family

### Requirement: Deferred follow-on modeling scope SHALL remain explicit
Docktap documentation SHALL state that daemon/internal phase taxonomy does not by itself define normalization, cross-plane correlation, healthcheck interpretation, or anomaly guidance.

#### Scenario: Event normalization remains deferred
- **WHEN** the taxonomy documentation describes task lifecycle or attach/stream families
- **THEN** it SHALL state that canonical event normalization remains future work

#### Scenario: Correlation and interpretation remain deferred
- **WHEN** the taxonomy documentation references healthcheck flows or API-path context
- **THEN** it SHALL state that API/internal correlation rules, healthcheck disambiguation, and housekeeping anomaly guidance remain future work

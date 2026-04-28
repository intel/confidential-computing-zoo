## ADDED Requirements

### Requirement: Secondary exec flows SHALL use a documented interpretation contract
Docktap documentation SHALL define how healthcheck-like exec flows are interpreted as secondary runtime activity in mixed Docker traces so they are not mistaken for primary workload lifecycle behavior.

#### Scenario: Secondary runtime interpretation uses normalized exec-task transitions
- **WHEN** mixed-trace documentation explains a healthcheck-like exec flow
- **THEN** it SHALL interpret that flow using normalized exec-task transitions rather than only raw daemon log fragments

#### Scenario: Incomplete evidence remains conservatively interpretable
- **WHEN** an exec flow has evidence of secondary runtime activity but lacks enough context for strong healthcheck identification
- **THEN** the documentation SHALL allow that flow to remain secondary-runtime or healthcheck-like rather than forcing a foreground-versus-healthcheck binary conclusion

### Requirement: Attach lifecycle lines SHALL be interpreted as stream or transport activity around exec flows
Docktap documentation SHALL describe attach lifecycle lines as stream or transport evidence around exec flows rather than as workload lifecycle states.

#### Scenario: Attach begin and end lines are treated as transport context
- **WHEN** `attach: stdout begin/end` or `attach: stderr begin/end` appear near an exec flow
- **THEN** the documentation SHALL describe them as transport or stream activity surrounding that exec flow

#### Scenario: Attach completion is not treated as workload completion
- **WHEN** `attach done` appears in a mixed trace
- **THEN** the documentation SHALL avoid treating it as the workload lifecycle completion event itself

### Requirement: Healthy healthcheck-like sequences SHALL define required and contextual evidence
Docktap documentation SHALL define a first-wave healthy healthcheck-like sequence using required normalized exec-task evidence and separate contextual evidence.

#### Scenario: Required runtime spine is documented
- **WHEN** the documentation describes a healthy healthcheck-like exec flow
- **THEN** it SHALL identify `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit` as the required runtime spine for that interpretation

#### Scenario: Contextual evidence is documented separately
- **WHEN** the documentation describes a healthy healthcheck-like exec flow
- **THEN** it SHALL describe attach lines, explicit healthcheck result lines, or repeated cadence as contextual evidence rather than as universally required proof

### Requirement: Secondary runtime anomalies SHALL remain narrowly scoped in the first wave
Docktap documentation SHALL define only a small first-wave anomaly surface for secondary runtime flows.

#### Scenario: Repeated exec failures are documented as anomalous
- **WHEN** a secondary-runtime or healthcheck-like exec flow repeatedly ends in failure
- **THEN** the documentation SHALL identify that pattern as worth later investigation

#### Scenario: Missing completion cues are documented as anomalous
- **WHEN** an exec flow shows `tasks/exec-started` without a corresponding exit, or attach begins without completion
- **THEN** the documentation SHALL identify that shape as a minimal anomalous secondary-runtime pattern

### Requirement: Parser and housekeeping concerns SHALL remain explicitly deferred
Docktap documentation SHALL state that secondary runtime interpretation does not by itself define parser implementation, machine confidence scoring, or housekeeping guidance.

#### Scenario: Parser concerns remain deferred
- **WHEN** the secondary-runtime interpretation contract is documented
- **THEN** it SHALL state that parser implementation and machine confidence modeling remain future work

#### Scenario: Housekeeping concerns remain deferred
- **WHEN** the interpretation contract references post-exec cleanup or daemon maintenance behavior
- **THEN** it SHALL state that housekeeping and cleanup guidance remain future work
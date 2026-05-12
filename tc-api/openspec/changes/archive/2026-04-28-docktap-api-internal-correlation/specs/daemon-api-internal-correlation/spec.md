## ADDED Requirements

### Requirement: API-path observations SHALL use a documented correlation contract with daemon/internal transitions
Docktap documentation SHALL define how proxy-observed API-path operations correlate with normalized daemon/internal runtime transitions in mixed Docker traces.

#### Scenario: Correlation rules target normalized internal transitions
- **WHEN** the documentation explains API-path to daemon/internal correlation
- **THEN** it SHALL correlate API observations to normalized daemon/internal transitions rather than only to raw daemon log templates

#### Scenario: Correlation remains distinct from classification
- **WHEN** correlation rules are documented
- **THEN** they SHALL be described as cross-plane joins rather than as replacements for API-path classification or daemon/internal normalization

### Requirement: Container create and start flows SHALL define documented correlation shapes
Docktap documentation SHALL define how container create and start observations correlate to the relevant daemon/internal preparation and task-lifecycle transitions.

#### Scenario: Container create correlation is documented
- **WHEN** `POST /containers/create` is documented in a mixed-trace context
- **THEN** the documentation SHALL describe how it relates to storage/mount preparation and subsequent container-task setup evidence

#### Scenario: Container start correlation is documented
- **WHEN** `POST /containers/{id}/start` is documented in a mixed-trace context
- **THEN** the documentation SHALL describe how it relates to runtime-spec or bundle preparation and to `tasks/start`

### Requirement: Exec flows SHALL define documented correlation shapes
Docktap documentation SHALL define how exec API observations correlate to normalized exec-task transitions without assigning healthcheck or foreground intent.

#### Scenario: Exec API observations correlate to exec-task transitions
- **WHEN** exec-related API observations are documented in a mixed trace
- **THEN** the documentation SHALL describe how they relate to `tasks/exec-added`, `tasks/exec-started`, and `tasks/exit`

#### Scenario: Exec correlation does not classify intent
- **WHEN** exec-path correlation rules are documented
- **THEN** they SHALL avoid deciding whether the correlated exec flow is healthcheck-driven or foreground workload activity

### Requirement: Correlation evidence SHALL distinguish canonical identifiers from contextual and fallback evidence
Docktap documentation SHALL describe correlation evidence in tiers so readers can distinguish stronger joins from weaker heuristics.

#### Scenario: Strong identifiers are documented
- **WHEN** correlation evidence is described
- **THEN** the documentation SHALL identify container identity and exec identity as stronger join evidence when available

#### Scenario: Fallback heuristics are documented separately
- **WHEN** stronger identifiers are unavailable or incomplete
- **THEN** the documentation SHALL identify contextual timing, namespace, operation shape, or adjacent runtime-preparation evidence as fallback correlation guidance rather than as canonical proof

### Requirement: Correlation outcomes SHALL preserve ambiguity when trace evidence is incomplete
Docktap documentation SHALL allow correlation outcomes to remain inferred or unresolved when mixed-trace evidence does not support a stronger join.

#### Scenario: Ambiguous correlation remains representable
- **WHEN** multiple plausible daemon/internal matches exist for one API observation
- **THEN** the documentation SHALL allow the correlation to remain inferred or ambiguous rather than forcing a single canonical match

#### Scenario: Unresolved correlation remains representable
- **WHEN** the trace does not provide enough evidence to join an API observation to a daemon/internal transition
- **THEN** the documentation SHALL allow that join to remain unresolved

### Requirement: Later interpretation concerns SHALL remain explicitly deferred
Docktap documentation SHALL state that API/internal correlation rules do not by themselves define parser implementation, attach-stream semantics, healthcheck interpretation, or housekeeping anomaly guidance.

#### Scenario: Parser and attach semantics remain deferred
- **WHEN** the correlation contract is documented
- **THEN** it SHALL state that parser implementation and attach-stream semantics remain future work

#### Scenario: Healthcheck and housekeeping interpretation remain deferred
- **WHEN** the correlation contract references exec or maintenance-related trace activity
- **THEN** it SHALL state that healthcheck intent and housekeeping anomaly guidance remain future work

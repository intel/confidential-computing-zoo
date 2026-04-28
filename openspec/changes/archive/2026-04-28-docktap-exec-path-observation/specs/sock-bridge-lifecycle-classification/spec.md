## ADDED Requirements

### Requirement: Docker exec API requests SHALL use explicit observation types
Docktap SHALL classify the primary Docker exec API create/start flow as explicit read-only observation types so command execution inside running containers is distinguishable from generic container inspection and fallback `unknown` traffic.

#### Scenario: Exec create is classified explicitly
- **WHEN** `POST /containers/{id}/exec` is processed
- **THEN** the request SHALL be classified as `exec_create`

#### Scenario: Exec start is classified explicitly
- **WHEN** `POST /exec/{id}/start` is processed
- **THEN** the request SHALL be classified as `exec_start`

### Requirement: Exec-path observations SHALL preserve minimal identifiers without changing lifecycle semantics
Docktap SHALL retain the target `container_id` and any available `exec_id` for exec-path observations and SHALL NOT promote exec traffic into lifecycle parent-linking or trusted-event submission.

#### Scenario: Exec create retains target container identity
- **WHEN** `POST /containers/{id}/exec` is processed
- **THEN** the observation metadata SHALL retain the target `container_id`

#### Scenario: Exec start retains exec identity from the API path
- **WHEN** `POST /exec/{id}/start` is processed
- **THEN** the observation metadata SHALL retain the target `exec_id`

#### Scenario: Exec observations remain outside lifecycle submission
- **WHEN** an `exec_create` or `exec_start` request is processed
- **THEN** it SHALL NOT create or mutate pull/create/start/stop/rm parent-chain linkage
- **THEN** it SHALL remain outside `SUBMITTABLE_OPERATIONS`

### Requirement: Deferred exec inspection scope SHALL be explicit
Docktap SHALL either classify follow-up exec inspection paths explicitly in a later change or document them as intentionally deferred, rather than leaving their omission implicit.

#### Scenario: Follow-up exec inspection is intentionally deferred in this change
- **WHEN** `GET /exec/{id}/json` is not classified by this change
- **THEN** the architecture and API docs SHALL identify that endpoint as a deferred observation boundary
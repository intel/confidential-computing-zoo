## ADDED Requirements

### Requirement: Container list requests SHALL use an explicit observation type
Docktap SHALL classify `GET /containers/json` and `GET /v*/containers/json` as `container_list` so container collection queries are distinguishable from container detail inspection.

#### Scenario: Unversioned container list is classified explicitly
- **WHEN** `GET /containers/json` is processed
- **THEN** the request SHALL be classified as `container_list`

#### Scenario: Versioned container list is classified explicitly
- **WHEN** `GET /v*/containers/json` is processed
- **THEN** the request SHALL be classified as `container_list`

### Requirement: Container list observations SHALL preserve query metadata without changing lifecycle semantics
Docktap SHALL retain container-list query parameters as structured observation metadata and SHALL NOT promote `container_list` into lifecycle parent-linking or trusted-event submission.

#### Scenario: `docker ps -a` remains distinguishable from default list traffic
- **WHEN** `GET /v*/containers/json?all=1` is processed
- **THEN** the request SHALL be classified as `container_list`
- **THEN** the structured metadata SHALL retain the `all=1` query parameter

#### Scenario: Container list does not join lifecycle parent chains
- **WHEN** a `container_list` request is processed
- **THEN** it SHALL NOT create or mutate pull/create/start/stop/rm parent-chain linkage
- **THEN** it SHALL remain outside `SUBMITTABLE_OPERATIONS`
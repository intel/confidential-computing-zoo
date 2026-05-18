## MODIFIED Requirements

### Requirement: Canonical Lifecycle Visibility
Docktap SHALL expose deterministic operation typing for canonical lifecycle requests used by Docker client preflight and runtime orchestration.

#### Scenario: Preflight ping is classified deterministically
- **WHEN** `GET /_ping` is processed
- **THEN** the request is classified by the documented lifecycle policy and not emitted as ambiguous `unknown`

#### Scenario: Image preflight inspect is classified deterministically
- **WHEN** `GET /v*/images/<image>/json` returns `404` prior to pull
- **THEN** the request is classified by the documented lifecycle policy and logged as an expected pre-pull check

#### Scenario: Network probe is classified explicitly
- **WHEN** `GET /v*/networks/<id>` is processed
- **THEN** the request is classified as `network_inspect`

#### Scenario: Volume probe is classified explicitly
- **WHEN** `GET /v*/volumes/<name>` is processed
- **THEN** the request is classified as `volume_inspect`

#### Scenario: Plugin probe is classified explicitly
- **WHEN** `GET /v*/plugins/<name>/json` is processed
- **THEN** the request is classified as `plugin_inspect`

#### Scenario: Container detail inspect remains unchanged
- **WHEN** `GET /v*/containers/<id>/json` is processed
- **THEN** the request remains classified as `inspect`

#### Scenario: Selected probe-style `404` responses use benign miss semantics
- **WHEN** `image_inspect`, `network_inspect`, `volume_inspect`, or `plugin_inspect` receives a daemon `404` response
- **THEN** the request remains classified by resource family
- **THEN** the local observation outcome SHALL be recorded as `miss`

## ADDED Requirements

### Requirement: Observation responses SHALL encode stable local outcomes
Docktap SHALL record a stable local observation outcome for selected read-only probe responses so expected misses are distinguishable from true errors without changing trusted lifecycle submission semantics.

#### Scenario: Successful probe response is recorded as ok
- **WHEN** `image_inspect`, `network_inspect`, `volume_inspect`, or `plugin_inspect` receives a daemon response with a success status
- **THEN** the local observation outcome SHALL be recorded as `ok`

#### Scenario: Selected probe-style `404` is recorded as miss
- **WHEN** `image_inspect`, `network_inspect`, `volume_inspect`, or `plugin_inspect` receives a daemon `404` response
- **THEN** the local observation outcome SHALL be recorded as `miss`

#### Scenario: Non-benign daemon failure is recorded as error
- **WHEN** a selected probe-style observation receives a daemon response outside the configured benign-miss case
- **THEN** the local observation outcome SHALL be recorded as `error`

#### Scenario: Proxy-local failure remains distinguishable from daemon miss
- **WHEN** Docktap fails before a daemon response is obtained or must synthesize an error response for malformed request, timeout, or forwarding failure
- **THEN** the local observation outcome SHALL be recorded as `error`
- **THEN** the recorded metadata SHALL remain distinguishable from a daemon-level `404` benign miss

### Requirement: Trusted lifecycle result semantics SHALL remain unchanged
Docktap SHALL keep local observation outcome semantics separate from trusted lifecycle result semantics.

#### Scenario: Observation outcome does not widen trusted submission scope
- **WHEN** a read-only probe observation records `ok`, `miss`, or `error`
- **THEN** it SHALL NOT become eligible for TruCon trusted-event submission solely because of the new outcome field

#### Scenario: TruCon lifecycle result remains separate
- **WHEN** Docktap emits trusted lifecycle events for `pull`, `create`, `start`, `stop`, or `rm`
- **THEN** the existing TruCon `operation_result` semantics SHALL remain unchanged by this observation outcome change
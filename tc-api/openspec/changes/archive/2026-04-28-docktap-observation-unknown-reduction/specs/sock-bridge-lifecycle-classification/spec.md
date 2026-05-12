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

#### Scenario: Versioned container logs are classified explicitly
- **WHEN** `GET /v*/containers/<id>/logs` is processed
- **THEN** the request is classified as an explicit read-only observation type rather than `unknown`

## ADDED Requirements

### Requirement: Unknown fallback SHALL remain an intentional observation boundary
Docktap SHALL keep the `unknown` classification as a deliberate fallback for unmapped Docker API requests rather than an accidental overflow bucket.

#### Scenario: Deferred read-only endpoints remain documented
- **WHEN** some read-only Docker API endpoints still remain unmapped after this change
- **THEN** the Docktap architecture and API documentation SHALL identify them as intentionally deferred `unknown` cases

#### Scenario: Explicit observation additions do not change trusted submission scope
- **WHEN** a common read-only endpoint is promoted from `unknown` to an explicit observation type
- **THEN** it SHALL remain outside trusted lifecycle submission unless a separate change modifies that contract
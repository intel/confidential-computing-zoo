## MODIFIED Requirements

### Requirement: Delegation TTL management
Delegation events SHALL have an `expires_at` field. The default TTL SHALL be supplied by tc-api/Docktap service-side policy. The default TTL SHALL remain configurable via environment variable `DOCKTAP_DELEGATION_TTL_SECONDS`. Callers using the primary authorization-readiness path SHALL NOT need to estimate task duration or provide a TTL in order to receive the service default.

#### Scenario: Delegation expires after TTL
- **WHEN** the current time exceeds a delegation's `expires_at`
- **THEN** the system SHALL treat the delegation as invalid and refuse to authorize operations referencing it

#### Scenario: Custom TTL via environment variable
- **WHEN** `DOCKTAP_DELEGATION_TTL_SECONDS` is set to `7200`
- **THEN** newly created delegations SHALL have `expires_at` set to creation time + 7200 seconds

#### Scenario: Readiness path uses service default TTL
- **WHEN** a caller uses the primary Docktap authorization-readiness flow without supplying a TTL override
- **THEN** the system SHALL create any needed delegation using the current service-side default TTL

### Requirement: Delegation scope constrains operation types
The delegation `scope` field SHALL be a list of allowed operation types (subset of `pull`, `create`, `start`, `stop`, `rm`). Operations not in scope SHALL be rejected. The default delegation scope used by the primary authorization-readiness path SHALL be supplied by tc-api/Docktap service-side policy when callers do not specify a scope.

#### Scenario: Operation within scope
- **WHEN** a `docker pull` is attempted and the active delegation has `scope: ["pull", "create", "start", "stop", "rm"]`
- **THEN** the system SHALL allow the operation

#### Scenario: Operation outside scope
- **WHEN** a `docker rm` is attempted and the active delegation has `scope: ["pull", "create"]`
- **THEN** the system SHALL reject the operation with attestation required response

#### Scenario: Readiness path uses service default scope
- **WHEN** a caller uses the primary Docktap authorization-readiness flow without supplying an explicit scope
- **THEN** the system SHALL create any needed delegation using the current service-side default scope

### Requirement: Delegation API endpoint
The system SHALL expose `POST /api/docktap/delegate` which accepts an OIDC identity token and creates a delegation event on the specified chain. This endpoint SHALL remain available as a lower-level operator and debugging path even when higher-level readiness flows become the preferred integration surface.

#### Scenario: Successful delegation creation
- **WHEN** a valid OIDC token is provided to `POST /api/docktap/delegate` with `chain_id`
- **THEN** the system SHALL create a delegation chain event, store the delegation in SQLite, and return the `delegation_id` and `expires_at`

#### Scenario: Expired token rejected
- **WHEN** an expired OIDC token is provided to `POST /api/docktap/delegate`
- **THEN** the system SHALL return HTTP 401 with an error indicating token expiry

#### Scenario: Raw delegation remains available alongside readiness flow
- **WHEN** a caller chooses the raw delegation API instead of the higher-level readiness path
- **THEN** the system SHALL continue to support explicit delegation creation for operator/debug usage
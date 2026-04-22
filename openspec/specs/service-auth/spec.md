## Purpose

Define the requirements for authenticating and authorizing internal TruCon callers across tc_api, Docktap, and compatibility paths.

## Requirements

### Requirement: TruCon token validation middleware
TruCon SHALL authenticate internal callers before dispatching to endpoint handlers. In the same-machine Phase B model, the primary authentication mechanism SHALL be Linux peer credentials from the shared Unix socket transport. If an HTTP compatibility path remains enabled during migration, that path MAY continue to validate a Bearer token from `TRUCON_SERVICE_TOKEN`.

#### Scenario: Valid peer credentials accepted
- **WHEN** a request arrives over the configured Unix socket from a recognized internal caller
- **THEN** TruCon SHALL authenticate the request using peer credentials and forward it to the endpoint handler normally

#### Scenario: Unrecognized Unix socket caller rejected
- **WHEN** a request arrives over the configured Unix socket but TruCon cannot map the peer context to an allowed internal caller
- **THEN** TruCon SHALL reject the request before endpoint dispatch

#### Scenario: Compatibility HTTP path validates token
- **WHEN** the compatibility HTTP path is enabled and a request arrives with header `Authorization: Bearer <valid-token>`
- **THEN** TruCon SHALL forward the request to the endpoint handler normally

#### Scenario: Invalid compatibility token rejected
- **WHEN** the compatibility HTTP path is enabled and a request arrives with an invalid or missing required Bearer token
- **THEN** TruCon SHALL reject the request before endpoint dispatch

### Requirement: Development mode bypass
TruCon SHALL support disabling internal authentication for development and test environments via explicit configuration.

#### Scenario: Auth disabled skips caller validation
- **WHEN** the authentication bypass setting is enabled for development or test use
- **THEN** TruCon SHALL accept requests without enforcing peer-credential or compatibility-token validation

#### Scenario: Startup warning when auth disabled
- **WHEN** TruCon starts with authentication bypass enabled
- **THEN** it SHALL log a WARNING-level message indicating that service authentication is disabled

#### Scenario: Startup refusal when required auth config missing
- **WHEN** TruCon starts with authentication enabled but the configured internal auth path cannot validate callers
- **THEN** it SHALL log an error and refuse to start

### Requirement: tc_api client credential attachment
tc_api's internal TruCon client SHALL use the configured same-machine authentication path for all outgoing TruCon requests. In the Phase B steady state, tc_api SHALL authenticate by connecting over the shared Unix socket transport.

#### Scenario: tc_api uses Unix socket auth path
- **WHEN** tc_api sends a commit or query request to TruCon with Phase B transport enabled
- **THEN** the request SHALL use the shared Unix socket transport rather than relying on a Bearer token header

#### Scenario: tc_api compatibility request attaches token only during migration
- **WHEN** tc_api uses the explicitly enabled compatibility HTTP path and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL include the expected Bearer token

### Requirement: Docktap client credential attachment
Docktap's internal TruCon client SHALL use the configured same-machine authentication path for all outgoing TruCon requests. In the Phase B steady state, Docktap SHALL authenticate by connecting over the shared Unix socket transport.

#### Scenario: Docktap uses Unix socket auth path
- **WHEN** Docktap sends a commit request to TruCon with Phase B transport enabled
- **THEN** the request SHALL use the shared Unix socket transport rather than relying on a Bearer token header

#### Scenario: Docktap compatibility request attaches token only during migration
- **WHEN** Docktap uses the explicitly enabled compatibility HTTP path and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL include the expected Bearer token

### Requirement: TruCon SHALL derive caller identity for internal policy and audit
TruCon SHALL derive a caller identity for authenticated internal requests that distinguishes at least `tc_api` and `docktap`. This identity SHALL be available to admission policy and audit logging.

#### Scenario: Caller identity recorded for authenticated request
- **WHEN** an internal request is successfully authenticated
- **THEN** TruCon SHALL associate the request with a caller identity that includes the caller service classification

#### Scenario: Caller identity remains internal-only
- **WHEN** TruCon processes a request with derived caller identity
- **THEN** that identity SHALL be treated as an internal admission and audit concept rather than part of the DSSE predicate or exported attested evidence contract

### Requirement: TruCon SHALL enforce a minimal caller authorization matrix
TruCon SHALL enforce endpoint access according to caller identity. At minimum, tc_api SHALL retain full internal access while Docktap SHALL be limited to commit-oriented operations unless an explicit requirement expands that scope.

#### Scenario: tc_api can access initialization and query surfaces
- **WHEN** an authenticated tc_api request targets internal initialization, commit, or query endpoints
- **THEN** TruCon SHALL authorize the request according to normal endpoint behavior

#### Scenario: Docktap is restricted from admin-style endpoints
- **WHEN** an authenticated Docktap request targets chain-initialization or other non-commit administrative endpoints
- **THEN** TruCon SHALL reject the request as unauthorized

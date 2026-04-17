### Requirement: TruCon token validation middleware
TruCon SHALL validate a Bearer token on every incoming HTTP request before dispatching to the endpoint handler. The token SHALL be read from the `TRUCON_SERVICE_TOKEN` environment variable at process startup.

#### Scenario: Valid token accepted
- **WHEN** a request arrives with header `Authorization: Bearer <valid-token>` and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL be forwarded to the endpoint handler normally

#### Scenario: Missing Authorization header
- **WHEN** a request arrives without an `Authorization` header and `TRUCON_AUTH_DISABLED` is not `true`
- **THEN** TruCon SHALL respond with HTTP 401 and body `{"detail": "Missing Authorization header"}`

#### Scenario: Wrong authorization scheme
- **WHEN** a request arrives with an `Authorization` header that does not start with `Bearer `
- **THEN** TruCon SHALL respond with HTTP 401 and body `{"detail": "Invalid Authorization scheme, expected Bearer"}`

#### Scenario: Invalid token value
- **WHEN** a request arrives with `Authorization: Bearer <token>` where `<token>` does not match `TRUCON_SERVICE_TOKEN`
- **THEN** TruCon SHALL respond with HTTP 401 and body `{"detail": "Invalid service token"}`

#### Scenario: Token comparison is constant-time
- **WHEN** token validation occurs
- **THEN** the comparison MUST use `hmac.compare_digest` or equivalent constant-time comparison to prevent timing side-channel attacks

### Requirement: Development mode bypass
TruCon SHALL support disabling authentication via the `TRUCON_AUTH_DISABLED` environment variable for development and test environments.

#### Scenario: Auth disabled skips validation
- **WHEN** `TRUCON_AUTH_DISABLED` is set to `true` (case-insensitive)
- **THEN** TruCon SHALL accept all requests regardless of `Authorization` header presence or value

#### Scenario: Startup warning when auth disabled
- **WHEN** TruCon starts with `TRUCON_AUTH_DISABLED=true`
- **THEN** TruCon SHALL log a WARNING-level message containing "service authentication DISABLED"

#### Scenario: Startup warning when token not configured
- **WHEN** TruCon starts with `TRUCON_AUTH_DISABLED` not set to `true` and `TRUCON_SERVICE_TOKEN` is empty or unset
- **THEN** TruCon SHALL log an ERROR-level message and refuse to start

### Requirement: tc_api client credential attachment
tc_api's `TrustedLogAPI` SHALL attach the service token to all outgoing TruCon HTTP requests.

#### Scenario: Token attached to commit request
- **WHEN** `TrustedLogAPI._post_to_trucon()` sends a request and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL include header `Authorization: Bearer <TRUCON_SERVICE_TOKEN>`

#### Scenario: Token attached to status and state queries
- **WHEN** `TrustedLogAPI.get_commit_queue_status()` or any TruCon GET query is sent and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL include header `Authorization: Bearer <TRUCON_SERVICE_TOKEN>`

#### Scenario: Missing token does not prevent request in dev mode
- **WHEN** `TRUCON_SERVICE_TOKEN` is empty or unset
- **THEN** the request SHALL be sent without an `Authorization` header (relying on TruCon's `TRUCON_AUTH_DISABLED` setting)

### Requirement: Docktap client credential attachment
Docktap's `TruConCommitter` SHALL attach the service token to all outgoing TruCon HTTP requests.

#### Scenario: Token attached to Docktap commit
- **WHEN** `TruConCommitter._post_to_trucon()` sends a request and `TRUCON_SERVICE_TOKEN` is set
- **THEN** the request SHALL include header `Authorization: Bearer <TRUCON_SERVICE_TOKEN>`

#### Scenario: Missing token does not block Docktap
- **WHEN** `TRUCON_SERVICE_TOKEN` is empty or unset
- **THEN** the request SHALL be sent without an `Authorization` header (Docktap's best-effort policy applies — failure is logged as warning)

### Requirement: Token generation at startup
The CVM startup script SHALL generate a cryptographically random service token and export it as `TRUCON_SERVICE_TOKEN` for all service processes.

#### Scenario: Token generated and exported
- **WHEN** `start.sh` (or `trust_service.sh`) executes
- **THEN** it SHALL generate a token using `python3 -c "import secrets; print(secrets.token_urlsafe(32))"` (or equivalent) and `export TRUCON_SERVICE_TOKEN=<generated>`

#### Scenario: Token inherited by child processes
- **WHEN** tc_api, TruCon, and Docktap are started as child processes of the startup script
- **THEN** each process SHALL inherit `TRUCON_SERVICE_TOKEN` from the environment

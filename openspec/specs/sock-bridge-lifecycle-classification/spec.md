# sock-bridge-lifecycle-classification Specification

## Purpose
TBD - created by archiving change normalize-sock-bridge-lifecycle-classification. Update Purpose after archive.
## Requirements
### Requirement: Complete Request Forwarding
Docktap SHALL fully read and forward each client HTTP request, including body bytes indicated by request framing, before sending the request to the Docker daemon.

#### Scenario: Forward complete JSON create body
- **WHEN** a client sends `POST /v*/containers/create` with a non-empty JSON body split across multiple socket reads
- **THEN** docktap forwards the complete body to Docker without truncation

#### Scenario: Header-only request does not block unnecessarily
- **WHEN** a client sends a request with no body (`Content-Length: 0` or no body semantics)
- **THEN** docktap forwards the request after header parsing within normal timeout bounds

### Requirement: Unified Operation Classification
Docktap SHALL use a single operation classification contract for all operation logging paths so that each request path/method resolves to one consistent operation type.

#### Scenario: Callback and structured record agree
- **WHEN** a request is processed and both callback logging and structured operation logging are emitted
- **THEN** both records contain the same operation type label for that request

#### Scenario: Container create uses canonical label
- **WHEN** `POST /v*/containers/create` is processed
- **THEN** the operation type is `create` and not an alternative alias such as `run`

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

#### Scenario: Versioned container logs are classified explicitly
- **WHEN** `GET /v*/containers/<id>/logs` is processed
- **THEN** the request is classified as an explicit read-only observation type rather than `unknown`

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

### Requirement: Version-Aware Streaming Detection
Docktap SHALL apply streaming response handling rules to versioned Docker API endpoints that require long-lived/stream-style behavior.

#### Scenario: Versioned wait endpoint uses streaming timeout policy
- **WHEN** `POST /v*/containers/<id>/wait` is processed
- **THEN** docktap uses streaming-oriented idle and duration bounds rather than non-stream short bounds

#### Scenario: Versioned logs endpoint uses streaming timeout policy
- **WHEN** `GET /v*/containers/<id>/logs?...` is processed
- **THEN** docktap keeps the response stream open according to streaming timeout policy until stream idle/deadline conditions are met

### Requirement: Unknown fallback SHALL remain an intentional observation boundary
Docktap SHALL keep the `unknown` classification as a deliberate fallback for unmapped Docker API requests rather than an accidental overflow bucket.

#### Scenario: Deferred read-only endpoints remain documented
- **WHEN** some read-only Docker API endpoints still remain unmapped after this change
- **THEN** the Docktap architecture and API documentation SHALL identify them as intentionally deferred `unknown` cases

#### Scenario: Explicit observation additions do not change trusted submission scope
- **WHEN** a common read-only endpoint is promoted from `unknown` to an explicit observation type
- **THEN** it SHALL remain outside trusted lifecycle submission unless a separate change modifies that contract

### Requirement: Unknown Request Passthrough
Docktap SHALL passthrough requests that do not match identified operation mappings, while classifying them as `unknown` for observability.

#### Scenario: Unidentified endpoint is forwarded unchanged
- **WHEN** a valid Docker API request does not match an identified operation type
- **THEN** docktap forwards the request and response without method/path/body rewriting or policy-based blocking

#### Scenario: Unknown request remains out of operation chain linking
- **WHEN** an unidentified request is processed
- **THEN** it is logged as `unknown` and does not create or mutate pull/create/start/stop/rm parent-chain linkage


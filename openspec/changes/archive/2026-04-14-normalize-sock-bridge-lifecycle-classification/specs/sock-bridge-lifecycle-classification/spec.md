## ADDED Requirements

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

### Requirement: Version-Aware Streaming Detection
Docktap SHALL apply streaming response handling rules to versioned Docker API endpoints that require long-lived/stream-style behavior.

#### Scenario: Versioned wait endpoint uses streaming timeout policy
- **WHEN** `POST /v*/containers/<id>/wait` is processed
- **THEN** docktap uses streaming-oriented idle and duration bounds rather than non-stream short bounds

#### Scenario: Versioned logs endpoint uses streaming timeout policy
- **WHEN** `GET /v*/containers/<id>/logs?...` is processed
- **THEN** docktap keeps the response stream open according to streaming timeout policy until stream idle/deadline conditions are met

### Requirement: Unknown Request Passthrough
Docktap SHALL passthrough requests that do not match identified operation mappings, while classifying them as `unknown` for observability.

#### Scenario: Unidentified endpoint is forwarded unchanged
- **WHEN** a valid Docker API request does not match an identified operation type
- **THEN** docktap forwards the request and response without method/path/body rewriting or policy-based blocking

#### Scenario: Unknown request remains out of operation chain linking
- **WHEN** an unidentified request is processed
- **THEN** it is logged as `unknown` and does not create or mutate pull/create/start/stop/rm parent-chain linkage

## ADDED Requirements

### Requirement: Docktap submits lifecycle events to TruCon
Docktap SHALL submit signed DSSE bundles to TruCon `POST /commit` for each Docker lifecycle operation of type `pull`, `create`, `start`, `stop`, or `rm`. Each operation SHALL produce exactly one independent commit. Operations of other types (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) SHALL NOT be submitted.

#### Scenario: Pull operation submitted
- **WHEN** Docktap intercepts a Docker `pull` operation and receives a successful response from the daemon
- **THEN** Docktap constructs Entry pairs from the operation metadata (operation_type, image_name, image_tag, image_digest), signs a DSSE bundle, and POSTs it to TruCon `/commit` with `chain_id="default"`

#### Scenario: Create operation submitted
- **WHEN** Docktap intercepts a Docker `create` operation and receives a successful response
- **THEN** Docktap submits a signed commit containing operation_type, image_name, container_name, and container_id entries

#### Scenario: Start/stop/rm operations submitted
- **WHEN** Docktap intercepts a Docker `start`, `stop`, or `rm` operation and receives a response
- **THEN** Docktap submits a signed commit containing operation_type and container_id entries

#### Scenario: Non-lifecycle operation skipped
- **WHEN** Docktap intercepts a Docker operation of type `wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, or `unknown`
- **THEN** Docktap SHALL NOT submit any commit to TruCon for that operation

### Requirement: Signing uses shared OIDC credentials
Docktap SHALL use the same OIDC credential acquisition mechanism as tc_api (`sigstore.oidc.detect_credential()`) to sign DSSE bundles. The OIDC token SHALL be acquired fresh on each commit call. The DSSE predicate format, entry digest computation, and event digest computation SHALL be identical to tc_api's existing signing path.

#### Scenario: DSSE bundle format matches tc_api
- **WHEN** Docktap constructs a DSSE bundle for a Docker operation
- **THEN** the bundle uses predicate type `https://trusted-log.dev/v1`, two-level SHA-384 digest computation, and Sigstore offline signing — identical to tc_api's `TrustedLogAPI.commit_record()`

### Requirement: Best-effort submission semantics
TruCon submission failures SHALL NOT block or delay Docker API responses. If the TruCon commit fails (network error, HTTP error, signing error, or timeout), Docktap SHALL log a warning with the operation type and error details, and continue normal proxy operation.

#### Scenario: TruCon unreachable
- **WHEN** Docktap attempts to submit an event but TruCon is unreachable (connection refused or timeout)
- **THEN** Docktap logs a warning containing the operation type and error, and the Docker response has already been returned to the CLI unaffected

#### Scenario: TruCon returns error
- **WHEN** TruCon returns an HTTP error status (4xx or 5xx) for a commit
- **THEN** Docktap logs a warning with the HTTP status and response body, and continues operation

#### Scenario: OIDC credential unavailable
- **WHEN** the ambient OIDC credential source is unavailable during a commit attempt
- **THEN** Docktap logs a warning and skips the commit without affecting Docker proxy behavior

### Requirement: Submission occurs after Docker response
Docktap SHALL return the Docker daemon response to the CLI before attempting the TruCon commit. The commit call SHALL occur after response streaming is complete and after the operation record is enriched from the response.

#### Scenario: Response returned before commit
- **WHEN** Docktap intercepts a `create` operation
- **THEN** the Docker response (including container ID) is fully streamed back to the CLI before the TruCon commit HTTP call begins

### Requirement: Cross-source sequence ordering
Events submitted by Docktap and events submitted by tc_api REST workers on the same chain SHALL receive monotonically increasing `sequence_num` values from TruCon's serialized commit path.

#### Scenario: Interleaved Docktap and REST commits
- **WHEN** Docktap submits a `start` event and a REST worker submits a `build` event concurrently on `chain_id="default"`
- **THEN** both events receive distinct `sequence_num` values and the sequence is strictly monotonic with no gaps

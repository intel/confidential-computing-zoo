## MODIFIED Requirements

### Requirement: Best-effort submission semantics
TruCon submission failures SHALL NOT block or delay Docker API responses. Docktap SHALL return the Docker daemon response to the CLI before any retry processing begins. If the initial TruCon commit attempt fails due to a transient transport or server-side error, Docktap SHALL enqueue the submission for bounded asynchronous retry using the same logical commit intent and idempotency key until TruCon acknowledges the `/commit` request or the retry policy is exhausted. Acknowledgement SHALL mean a successful TruCon `/commit` response accepting the event into TruCon's queue; immutable-backend confirmation is out of scope for Docktap. If retry attempts are exhausted, Docktap SHALL mark the submission as terminally failed in its local retry state and log the failure for operators, without retroactively failing the already-completed Docker API response.

#### Scenario: Transient TruCon failure is retried after response
- **WHEN** Docktap has already returned a successful Docker response to the CLI and the initial `POST /commit` attempt fails with a transient network or HTTP 5xx error
- **THEN** Docktap SHALL record a retryable local submission item and retry it asynchronously according to a bounded retry policy

#### Scenario: Retry reuses the original commit intent
- **WHEN** Docktap retries a previously failed submission
- **THEN** it SHALL reuse the same event payload identity and idempotency key so repeated `/commit` attempts represent one logical TruCon commit

#### Scenario: TruCon acknowledgement ends Docktap retry responsibility
- **WHEN** a retry attempt receives a successful TruCon `/commit` response with accepted commit metadata
- **THEN** Docktap SHALL mark the submission as acknowledged and SHALL stop retrying it

#### Scenario: Terminal retry exhaustion does not change Docker CLI result
- **WHEN** a submission reaches the maximum retry limit without receiving TruCon acknowledgement
- **THEN** Docktap SHALL mark the submission as terminally failed and log the failure context
- **THEN** the previously returned Docker CLI response SHALL remain unaffected

#### Scenario: Non-blocking proxy behavior is preserved
- **WHEN** Docktap intercepts a Docker lifecycle request and the associated TruCon submission enters retry handling
- **THEN** Docker response latency SHALL remain decoupled from retry completion and immutable-backend confirmation
## 1. REST Control-Plane Compatibility Coverage

- [x] 1.1 Add a shared integration-test harness for build/publish/launch flows that stubs external command and signing dependencies while preserving endpoint-visible response models
- [x] 1.2 Add build-flow integration tests covering both normal TruCon commit success and degraded commit failure without breaking build result/status fields
- [x] 1.3 Add publish-flow integration tests covering both normal TruCon commit success and degraded commit failure without breaking publish result/status fields
- [x] 1.4 Add launch-flow integration tests covering both normal TruCon commit success and degraded commit failure without breaking launch result/status fields

## 2. Docktap Retry and Acknowledgement Handling

- [x] 2.1 Introduce Docktap-local submission state that records retryable pending commits with stable idempotency keys after the Docker response is returned
- [x] 2.2 Implement bounded asynchronous retry/backoff processing that retries transient TruCon `/commit` failures until acknowledgement or retry exhaustion
- [x] 2.3 Mark acknowledged submissions as complete and exhausted submissions as terminally failed with operator-visible logging, without affecting Docker CLI responses
- [x] 2.4 Add Docktap tests covering transient failure retry, idempotency-key reuse across retries, acknowledgement completion, and terminal exhaustion behavior
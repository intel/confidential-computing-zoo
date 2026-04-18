## 1. TruCon Service Boundary and Contracts

- [x] 1.1 Define internal TruCon API contract for record init, entry append, commit, submit, and status query flows
- [x] 1.2 Define idempotency key rules and conflict behavior for repeated commit submissions
- [x] 1.3 Define queue lifecycle state model and transition rules for commit, retryable failure, confirmation, and terminal failure

## 2. REST Control-Plane Integration

- [x] 2.1 Identify current trusted-event write points in existing build/publish/launch control-plane flows
- [x] 2.2 Replace direct trusted-log mutation path with TruCon-boundary integration points while preserving current external API response behavior
- [x] 2.3 Add integration tests validating that build/publish/launch flows still return expected status fields while trusted events route through TruCon contracts

## 3. Docktap Process Integration

- [x] 3.1 Define Docktap event emission contract to TruCon for runtime interception and lifecycle events
- [x] 3.2 Add Docktap-side retry and acknowledgement handling for transient TruCon submission failures
- [x] 3.3 Add integration tests for concurrent event submissions from Docktap and REST workers against shared workload contexts

## 4. Instance Mapping Capability

- [x] 4.1 Define data model for workload-to-instance and instance-to-event mapping relationships
- [x] 4.2 Implement mapping lifecycle updates for instance start, restart, replacement, and termination events
- [x] 4.3 Add query coverage tests for workload-centric and instance-centric mapping lookups

## 5. Submission Reliability and Observability

- [x] 5.1 Implement queue worker retry/backoff behavior with bounded retry policy and failure classification
- [x] 5.2 Add operational metrics for queue depth, submission latency, retry counts, and confirmation lag
- [x] 5.3 Add TruCon-only rollout and degraded-mode runbook guidance covering process supervision, parity checks, and operator actions without legacy write-path fallback

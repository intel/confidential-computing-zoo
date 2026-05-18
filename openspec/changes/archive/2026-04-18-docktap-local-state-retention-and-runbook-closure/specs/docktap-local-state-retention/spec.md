## ADDED Requirements

### Requirement: Docktap local state must remain bounded without affecting replayability
Docktap SHALL garbage-collect local routing, mapping, and retry bookkeeping state without making trust-chain replay or verification depend on Docktap-local persistence. Replay correctness SHALL depend only on TruCon state and immutable backend state.

#### Scenario: Local cleanup does not change replay source of truth
- **WHEN** Docktap removes expired local routing, mapping, or retry records
- **THEN** replay and verification SHALL continue to rely on TruCon and immutable backend records rather than Docktap-local storage

### Requirement: Docktap shall run periodic local-state garbage collection
Docktap SHALL run a periodic background sweeper that evaluates all GC-eligible local state classes using configured retention settings.

#### Scenario: Periodic sweeper runs independently of traffic volume
- **WHEN** Docktap is running with low or no Docker API traffic
- **THEN** local-state garbage collection SHALL still execute at the configured sweep interval

### Requirement: Operation tracker retention is bounded by last access time
Docktap SHALL remove `OperationTracker` records whose `last_accessed` timestamp is older than the configured operation retention window.

#### Scenario: Expired operation record is removed
- **WHEN** an operation record has not been accessed for longer than the configured operation retention window
- **THEN** Docktap SHALL remove that record from the in-memory operation tracker during periodic garbage collection

### Requirement: Workload mappings remain until lifecycle termination and grace expiry
Docktap SHALL preserve persisted container-to-workload mappings for active containers and SHALL remove mappings only after the container has reached terminal lifecycle state and the configured removed-container grace window has elapsed. To support this, Docktap SHALL track `created_at`, `last_seen_at`, `removed_at`, and `last_operation` for each persisted mapping row.

#### Scenario: Active container mapping is preserved
- **WHEN** a container mapping has not reached `rm` terminal state
- **THEN** Docktap SHALL retain the mapping even if the record is older than the removed-container retention window

#### Scenario: Removed container mapping expires after grace window
- **WHEN** Docktap has recorded `rm` for a container and the configured removed-container retention window has elapsed since `removed_at`
- **THEN** Docktap SHALL delete that mapping row during periodic garbage collection

### Requirement: Retention settings shall be explicitly configurable
Docktap SHALL expose explicit retention configuration for sweep interval, operation tracker retention, removed-container mapping retention, acknowledged retry retention, and terminal retry retention.

#### Scenario: Operator tunes local retention behavior
- **WHEN** an operator sets Docktap retention environment variables
- **THEN** Docktap SHALL apply those values to the corresponding local-state cleanup policies without changing trust-chain replay semantics
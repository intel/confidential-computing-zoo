## Purpose

Define the requirements for querying workload instance mappings recorded by TruCon.

## Requirements

### Requirement: List instances for a workload
TruCon SHALL expose `GET /workloads/{workload_id}/instances` that returns all distinct instances with commit records in the given workload's chain.

#### Scenario: Workload with multiple instances
- **WHEN** a caller requests `GET /workloads/my-app/instances` and commit_queue contains records with `chain_id="my-app"` and distinct `instance_id` values `"abc123"` and `"def456"`
- **THEN** the response SHALL be a JSON array containing two `InstanceSummary` objects, each with `instance_id`, `first_event_at`, `last_event_at`, and `event_count` fields

#### Scenario: Workload with no instances
- **WHEN** a caller requests `GET /workloads/unknown-app/instances` and no records with that `chain_id` exist
- **THEN** the response SHALL be an empty JSON array `[]`

#### Scenario: Records without instance_id are excluded
- **WHEN** commit_queue contains records with `chain_id="my-app"` where some records have `instance_id=NULL`
- **THEN** the `GET /workloads/my-app/instances` response SHALL only include entries for non-NULL `instance_id` values

### Requirement: List events for an instance
TruCon SHALL expose `GET /instances/{instance_id}/events` that returns all commit records associated with the given container instance, ordered by `sequence_num` ascending.

#### Scenario: Instance with multiple events
- **WHEN** a caller requests `GET /instances/abc123/events` and commit_queue contains three records with `instance_id="abc123"`
- **THEN** the response SHALL be a JSON array of three `EventSummary` objects ordered by `sequence_num` ascending, each containing `record_id`, `event_id`, `sequence_num`, `status`, and `created_at`

#### Scenario: Unknown instance
- **WHEN** a caller requests `GET /instances/nonexistent/events`
- **THEN** the response SHALL be an empty JSON array `[]`

### Requirement: List all events for a workload
TruCon SHALL expose `GET /workloads/{workload_id}/events` that returns all commit records across all instances of a workload, ordered by `sequence_num` ascending.

#### Scenario: Workload events across multiple instances
- **WHEN** a caller requests `GET /workloads/my-app/events` and commit_queue contains records with `chain_id="my-app"` across instances `"abc123"` and `"def456"`
- **THEN** the response SHALL be a JSON array of all matching `EventSummary` objects (including `instance_id` field) ordered by `sequence_num` ascending

#### Scenario: Includes events without instance_id
- **WHEN** commit_queue contains records with `chain_id="my-app"` where some records have `instance_id=NULL`
- **THEN** `GET /workloads/my-app/events` SHALL include those records with `instance_id: null` in the response

### Requirement: Query endpoints require authentication
All new query endpoints SHALL enforce the same Bearer token authentication as existing TruCon endpoints.

#### Scenario: Unauthenticated request
- **WHEN** a caller sends `GET /workloads/my-app/instances` without an `Authorization` header
- **THEN** the response SHALL be `401 Unauthorized` with a descriptive JSON body

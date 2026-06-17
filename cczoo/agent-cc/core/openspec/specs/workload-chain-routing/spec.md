## MODIFIED Requirements

### Requirement: Workload identity extraction from container labels
Docktap SHALL extract the value of the `io.trucon.workload-id` label from the `docker create` request body when present. The extracted value SHALL be preserved as workload metadata for runtime evidence and query correlation, but it SHALL NOT select an independent measured chain. All RTMR-backed lifecycle commits SHALL use `chain_id="default"`.

#### Scenario: Create with workload label
- **WHEN** Docktap intercepts a `docker create` request whose body contains `Labels: {"io.trucon.workload-id": "my-app"}`
- **THEN** Docktap extracts `"my-app"` as `workload_id`, preserves it for subsequent container correlation, and submits the measured commit with `chain_id="default"`

#### Scenario: Create without workload label
- **WHEN** Docktap intercepts a `docker create` request whose body does not contain an `io.trucon.workload-id` label
- **THEN** Docktap uses `chain_id="default"` and records no workload-specific override metadata

#### Scenario: Create with empty workload label
- **WHEN** Docktap intercepts a `docker create` request with `Labels: {"io.trucon.workload-id": ""}`
- **THEN** Docktap treats the label as absent and uses `chain_id="default"`

### Requirement: SQLite-backed container-to-workload persistence
Docktap SHALL persist the mapping from `container_id` to `workload_id` in a local SQLite database at `/dev/shm/docktap/container_map.db`. The mapping SHALL be written during `docker create` processing and read during subsequent operations so later runtime events can carry consistent workload metadata even though all measured commits use the default chain.

#### Scenario: Mapping persisted on create
- **WHEN** Docktap processes a `docker create` with `io.trucon.workload-id="my-app"` and container_id `abc123`
- **THEN** a row `(container_id="abc123", workload_id="my-app")` is written to the `container_workload` table

#### Scenario: Mapping read on start
- **WHEN** Docktap processes a `docker start` for container_id `abc123` and the `container_workload` table contains `(abc123, "my-app")`
- **THEN** Docktap uses the stored `workload_id` for emitted metadata while still submitting the measured commit with `chain_id="default"`

#### Scenario: Mapping survives Docktap restart
- **WHEN** Docktap restarts (process restart, not host reboot), and a container_id `abc123` was previously mapped to `workload_id="my-app"`
- **THEN** Docktap reads the mapping from SQLite and uses `workload_id="my-app"` for subsequent metadata enrichment

#### Scenario: Mapping unavailable falls back to default metadata behavior
- **WHEN** Docktap processes a `docker stop` for container_id `xyz789` and no mapping exists in the `container_workload` table
- **THEN** Docktap submits the measured commit with `chain_id="default"` and omits workload-specific metadata inferred from the missing mapping

#### Scenario: Default-chain container not persisted
- **WHEN** Docktap processes a `docker create` without `io.trucon.workload-id` label
- **THEN** no row is written to the `container_workload` table for that container

### Requirement: Multiple containers share one workload chain
Multiple containers labeled with the same `io.trucon.workload-id` value SHALL share the same workload metadata value while still appending to the single default measured chain. Events from different workloads and containers SHALL interleave in one global commit-arrival order on `chain_id="default"`.

#### Scenario: Two containers same workload
- **WHEN** container_A and container_B are both created with `io.trucon.workload-id="my-app"`, and container_A starts before container_B starts
- **THEN** all four events (create_A, create_B, start_A, start_B) are submitted to `chain_id="default"` with strictly monotonic sequence numbers, and each event retains `workload_id="my-app"` metadata


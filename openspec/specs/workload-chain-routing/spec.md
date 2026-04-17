### Requirement: Workload identity extraction from container labels
Docktap SHALL extract the value of the `io.trucon.workload-id` label from the `docker create` request body when present. The extracted value SHALL be used as the `chain_id` for all lifecycle events associated with that container.

#### Scenario: Create with workload label
- **WHEN** Docktap intercepts a `docker create` request whose body contains `Labels: {"io.trucon.workload-id": "my-app"}`
- **THEN** Docktap extracts `"my-app"` as the workload_id and uses `chain_id="my-app"` for the create commit and all subsequent operations on that container

#### Scenario: Create without workload label
- **WHEN** Docktap intercepts a `docker create` request whose body does not contain an `io.trucon.workload-id` label
- **THEN** Docktap uses `chain_id="default"` for the create commit and all subsequent operations on that container

#### Scenario: Create with empty workload label
- **WHEN** Docktap intercepts a `docker create` request with `Labels: {"io.trucon.workload-id": ""}`
- **THEN** Docktap treats the label as absent and uses `chain_id="default"`

### Requirement: SQLite-backed container-to-workload persistence
Docktap SHALL persist the mapping from `container_id` to `workload_id` in a local SQLite database at `/dev/shm/docktap/container_map.db`. The mapping SHALL be written during `docker create` processing and read during subsequent operations.

#### Scenario: Mapping persisted on create
- **WHEN** Docktap processes a `docker create` with `io.trucon.workload-id="my-app"` and container_id `abc123`
- **THEN** a row `(container_id="abc123", workload_id="my-app")` is written to the `container_workload` table

#### Scenario: Mapping read on start
- **WHEN** Docktap processes a `docker start` for container_id `abc123` and the `container_workload` table contains `(abc123, "my-app")`
- **THEN** Docktap uses `chain_id="my-app"` for the start commit

#### Scenario: Mapping survives Docktap restart
- **WHEN** Docktap restarts (process restart, not host reboot), and a container_id `abc123` was previously mapped to `workload_id="my-app"`
- **THEN** Docktap reads the mapping from SQLite and uses `chain_id="my-app"` for subsequent operations on that container

#### Scenario: Mapping unavailable falls back to default
- **WHEN** Docktap processes a `docker stop` for container_id `xyz789` and no mapping exists in the `container_workload` table
- **THEN** Docktap uses `chain_id="default"` for the stop commit

#### Scenario: Default-chain container not persisted
- **WHEN** Docktap processes a `docker create` without `io.trucon.workload-id` label
- **THEN** no row is written to the `container_workload` table for that container

### Requirement: Database initialization on startup
Docktap SHALL create the SQLite database directory and `container_workload` table if they do not exist on startup. If the database already exists (Docktap restart), the existing data SHALL be preserved.

#### Scenario: First startup creates database
- **WHEN** Docktap starts and `/dev/shm/docktap/container_map.db` does not exist
- **THEN** Docktap creates the directory and database with the `container_workload` table

#### Scenario: Restart preserves data
- **WHEN** Docktap starts and `/dev/shm/docktap/container_map.db` already exists with rows
- **THEN** existing mappings are available for chain_id resolution

### Requirement: Pull operations use default chain
Pull operations SHALL always use `chain_id="default"` because they are image-level (not container-level) and carry no container labels.

#### Scenario: Pull always uses default chain
- **WHEN** Docktap intercepts a `docker pull` operation
- **THEN** Docktap submits the commit with `chain_id="default"` regardless of any workload context

### Requirement: Multiple containers share one workload chain
Multiple containers labeled with the same `io.trucon.workload-id` value SHALL submit events to the same chain. Events from different containers on the same chain interleave in commit-arrival order.

#### Scenario: Two containers same workload
- **WHEN** container_A and container_B are both created with `io.trucon.workload-id="my-app"`, and container_A starts before container_B starts
- **THEN** all four events (create_A, create_B, start_A, start_B) are submitted to `chain_id="my-app"` with strictly monotonic `sequence_num` values reflecting commit-arrival order

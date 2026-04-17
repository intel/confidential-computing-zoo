## MODIFIED Requirements

### Requirement: Docktap submits lifecycle events to TruCon
Docktap SHALL submit signed DSSE bundles to TruCon `POST /commit` for each Docker lifecycle operation of type `pull`, `create`, `start`, `stop`, or `rm`. Each operation SHALL produce exactly one independent commit. Operations of other types (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) SHALL NOT be submitted. The `chain_id` for each commit SHALL be resolved as follows: `pull` operations use `chain_id="default"`; `create` operations use the value of the `io.trucon.workload-id` container label if present and non-empty, otherwise `"default"`; `start`, `stop`, and `rm` operations use the `chain_id` previously resolved for that container_id, falling back to `"default"` if no mapping exists.

#### Scenario: Pull operation submitted
- **WHEN** Docktap intercepts a Docker `pull` operation and receives a successful response from the daemon
- **THEN** Docktap constructs Entry pairs from the operation metadata (operation_type, image_name, image_tag, image_digest), signs a DSSE bundle, and POSTs it to TruCon `/commit` with `chain_id="default"`

#### Scenario: Create operation submitted with workload label
- **WHEN** Docktap intercepts a Docker `create` operation with `io.trucon.workload-id="my-app"` and receives a successful response
- **THEN** Docktap submits a signed commit containing operation_type, image_name, container_name, and container_id entries with `chain_id="my-app"`

#### Scenario: Create operation submitted without workload label
- **WHEN** Docktap intercepts a Docker `create` operation without an `io.trucon.workload-id` label and receives a successful response
- **THEN** Docktap submits a signed commit containing operation_type, image_name, container_name, and container_id entries with `chain_id="default"`

#### Scenario: Start/stop/rm operations submitted with resolved chain
- **WHEN** Docktap intercepts a Docker `start`, `stop`, or `rm` operation for a container whose `workload_id` was previously resolved to `"my-app"`
- **THEN** Docktap submits a signed commit containing operation_type and container_id entries with `chain_id="my-app"`

#### Scenario: Start/stop/rm operations submitted with no mapping
- **WHEN** Docktap intercepts a Docker `start`, `stop`, or `rm` operation for a container with no persisted workload mapping
- **THEN** Docktap submits a signed commit containing operation_type and container_id entries with `chain_id="default"`

#### Scenario: Non-lifecycle operation skipped
- **WHEN** Docktap intercepts a Docker operation of type `wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, or `unknown`
- **THEN** Docktap SHALL NOT submit any commit to TruCon for that operation

### Requirement: Cross-source sequence ordering
Events submitted by Docktap and events submitted by tc_api REST workers on the same chain SHALL receive monotonically increasing `sequence_num` values from TruCon's serialized commit path.

#### Scenario: Interleaved Docktap and REST commits on workload chain
- **WHEN** Docktap submits a `start` event and a REST worker submits a `build` event concurrently on the same `chain_id` (e.g., `"my-app"`)
- **THEN** both events receive distinct `sequence_num` values and the sequence is strictly monotonic with no gaps

#### Scenario: Events on different chains are independently sequenced
- **WHEN** Docktap submits events to `chain_id="my-app"` and `chain_id="default"` concurrently
- **THEN** each chain maintains its own independent monotonic `sequence_num` sequence

## MODIFIED Requirements

### Requirement: Docktap submits lifecycle events to TruCon
Docktap SHALL submit signed DSSE bundles to TruCon `POST /commit` for each Docker lifecycle operation of type `pull`, `create`, `start`, `stop`, or `rm`. Each operation SHALL produce exactly one independent commit. Operations of other types (`wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, `unknown`) SHALL NOT be submitted. All measured commits SHALL use `chain_id="default"`. Workload, instance, image, and launch identity SHALL remain part of the emitted evidence payload rather than selecting separate measured chains.

#### Scenario: Pull operation submitted
- **WHEN** Docktap intercepts a Docker `pull` operation and receives a successful response from the daemon
- **THEN** Docktap constructs Entry pairs from the operation metadata (operation_type, image_name, image_tag, image_digest), signs a DSSE bundle, and POSTs it to TruCon `/commit` with `chain_id="default"`

#### Scenario: Create operation submitted with workload label
- **WHEN** Docktap intercepts a Docker `create` operation with `io.trucon.workload-id="my-app"` and receives a successful response
- **THEN** Docktap submits a signed commit containing operation_type, image_name, container_name, container_id, and workload metadata with `chain_id="default"`

#### Scenario: Start/stop/rm operations submitted with resolved workload metadata
- **WHEN** Docktap intercepts a Docker `start`, `stop`, or `rm` operation for a container whose `workload_id` was previously resolved to `"my-app"`
- **THEN** Docktap submits a signed commit containing operation_type, container_id, and workload metadata with `chain_id="default"`

#### Scenario: Non-lifecycle operation skipped
- **WHEN** Docktap intercepts a Docker operation of type `wait`, `rmi`, `image_inspect`, `inspect`, `preflight_ping`, `preflight_info`, or `unknown`
- **THEN** Docktap SHALL NOT submit any commit to TruCon for that operation

### Requirement: Cross-source sequence ordering
Events submitted by Docktap and events submitted by tc_api REST workers SHALL share one global monotonic `sequence_num` stream on the default measured chain. Workload identity SHALL NOT create an independent RTMR-backed sequence.

#### Scenario: Interleaved Docktap and REST commits share the default sequence
- **WHEN** Docktap submits a `start` event for workload `"my-app"` and a REST worker submits a `build` event for workload `"other-app"` concurrently
- **THEN** both events are committed on `chain_id="default"` with distinct strictly increasing `sequence_num` values reflecting global arrival order

#### Scenario: Different workloads do not create independent measured sequences
- **WHEN** Docktap emits runtime events for two different workload identities during the same node epoch
- **THEN** the resulting measured records still append to one default-chain RTMR history rather than to independent workload-scoped RTMR histories

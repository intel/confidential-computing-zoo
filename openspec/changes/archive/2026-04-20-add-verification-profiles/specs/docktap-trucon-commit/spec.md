## ADDED Requirements

### Requirement: Docktap runtime commits emit explicit audit outcomes
Docktap commits SHALL emit explicit operation outcomes for auditable runtime events rather than requiring verifiers to infer success or failure from transport context alone.

#### Scenario: Successful runtime operation emits outcome
- **WHEN** Docktap submits a successful `pull`, `create`, `start`, `stop`, or `rm` operation to TruCon
- **THEN** the emitted entries SHALL include `operation_result="success"`

#### Scenario: Failed or degraded runtime operation emits outcome
- **WHEN** Docktap emits an auditable runtime event whose Docker-side result is known to have failed or degraded
- **THEN** the emitted entries SHALL include an explicit non-success `operation_result` value suitable for runtime-profile evaluation

### Requirement: Docktap runtime commits emit profile-required identity fields
Docktap commits SHALL emit the minimum identity fields required by the runtime verification profile.

#### Scenario: Workload and instance identity emitted for container-scoped operation
- **WHEN** Docktap submits a container-scoped `create`, `start`, `stop`, or `rm` event
- **THEN** the emitted entries SHALL include `workload_id` and `instance_id` in addition to the operation type

#### Scenario: Image identity emitted for image-targeted runtime operation
- **WHEN** Docktap submits a `pull` or `create` operation whose audit meaning depends on the image target
- **THEN** the emitted entries SHALL include either `image_digest` or another stable image reference field suitable for runtime-profile evaluation

### Requirement: Docktap can attribute launch-related runtime events to the current launch boundary
When Docktap intercepts runtime events that belong to a REST-originated launch flow, it SHALL propagate the current `launch_id` so those runtime events can be grouped into the same launch verification set.

#### Scenario: Create and start events carry launch boundary
- **WHEN** Docktap intercepts `create` or `start` activity attributable to a current launch flow
- **THEN** the emitted entries SHALL include the corresponding `launch_id`

#### Scenario: Runtime events without launch attribution remain valid runtime evidence
- **WHEN** Docktap intercepts a runtime event that is not attributable to a known launch flow
- **THEN** the event MAY omit `launch_id`, and it SHALL remain valid for docktap-runtime verification under workload and instance identity alone
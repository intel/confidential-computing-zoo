## MODIFIED Requirements

### Requirement: Docktap runtime commits emit profile-required identity fields
Docktap commits SHALL emit the minimum identity fields required by the runtime verification profile, including explicit engine identity for every auditable runtime event.

#### Scenario: Workload and instance identity emitted for container-scoped operation
- **WHEN** Docktap submits a container-scoped `create`, `start`, `stop`, or `rm` event
- **THEN** the emitted entries SHALL include `workload_id` and `instance_id` in addition to the operation type

#### Scenario: Image identity emitted for image-targeted runtime operation
- **WHEN** Docktap submits a `pull` or `create` operation whose audit meaning depends on the image target
- **THEN** the emitted entries SHALL include either `image_digest` or another stable image reference field suitable for runtime-profile evaluation

#### Scenario: Every auditable runtime commit carries engine identity
- **WHEN** Docktap submits an auditable `pull`, `create`, `start`, `stop`, or `rm` event
- **THEN** the emitted entries SHALL include `runtime_engine` with the canonical identifier for the engine that produced the event

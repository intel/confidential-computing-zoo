## ADDED Requirements

### Requirement: REST producers emit profile-aligned build and publish audit fields
REST-originated trusted-log commits for `build` and `publish` flows SHALL emit the minimum identity and outcome fields required by the verification profiles rather than relying on raw command logs alone.

#### Scenario: Build flow emits stable audit identities
- **WHEN** a build flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `output_image_digest`, `dockerfile_digest`, `build_context_digest`, `base_image_digests`, and `build_status`

#### Scenario: Publish flow emits pushed subject identity
- **WHEN** a publish flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `pushed_subject_digest`, `target_ref`, and `publish_status`

### Requirement: REST launch commits use `launch_id` as the attempt boundary
REST-originated launch commits SHALL emit the existing `launch_id` as the authoritative v1 launch-attempt identity and SHALL include workload-scoped launch audit data keyed to that identifier.

#### Scenario: Launch flow emits launch boundary
- **WHEN** a launch flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `launch_id` and `workload_id`, and launch verification SHALL be able to treat that `launch_id` as the attempt boundary

#### Scenario: Launch failure before instance creation remains attributable
- **WHEN** a launch flow fails before any instance is created
- **THEN** the launch commit SHALL still contain `launch_id`, `workload_id`, and the failure outcome fields needed to audit that attempt without requiring `instance_id`

### Requirement: REST launch commits emit configuration digest and security projection
REST-originated launch commits SHALL emit both a stable launch configuration digest and explicit security-relevant launch fields.

#### Scenario: Launch flow emits required security projection
- **WHEN** a launch flow commits its trusted-log record
- **THEN** the emitted entries SHALL include `image_digest`, `launch_config_digest`, `privileged`, `network_mode`, `mounts`, `devices`, and `capabilities`

#### Scenario: Launch success emits resulting instance identity
- **WHEN** a launch flow successfully creates one or more container instances
- **THEN** the launch commit SHALL emit the resulting `instance_id` or instance identifier list associated with the same `launch_id`
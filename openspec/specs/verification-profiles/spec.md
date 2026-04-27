## Purpose

Define the canonical verification profiles for audited build, publish, launch, and docktap-runtime flows, including their required evidence and verdict semantics.

## Requirements

### Requirement: Canonical verification profiles for audited flows
The system SHALL define canonical verification profiles for `build`, `publish`, `launch`, and `docktap-runtime`. Each profile SHALL specify its required fields, hard-fail conditions, warning-only omissions, and verdict semantics.

#### Scenario: Profile contract exists for each supported flow
- **WHEN** an implementer or operator reads the verification profile specification
- **THEN** the contract SHALL define one distinct profile each for `build`, `publish`, `launch`, and `docktap-runtime`

#### Scenario: Profile semantics are testable
- **WHEN** a verifier evaluates a chain against a profile
- **THEN** the profile SHALL provide enough required-field and failure semantics to derive deterministic pass, warning, incomplete, or failure outcomes

### Requirement: Build profile defines stable artifact and input identity
The `build` verification profile SHALL require a stable output artifact identity and a bounded set of build input identities suitable for security audit.

#### Scenario: Build profile required identities
- **WHEN** a chain is evaluated under the `build` profile
- **THEN** the required fields SHALL include `output_image_digest`, `dockerfile_digest`, `build_context_digest`, and `base_image_digests`

#### Scenario: Build success without output identity fails
- **WHEN** a build flow reports success but omits `output_image_digest`
- **THEN** the `build` profile verdict SHALL be `failed`

#### Scenario: Missing optional SBOM identity warns
- **WHEN** a build flow otherwise satisfies the required fields but omits an optional SBOM-related digest or reference
- **THEN** the `build` profile verdict SHALL be `warning` rather than `failed`

### Requirement: Publish profile remains minimal but identity-bearing
The `publish` verification profile SHALL remain intentionally simple in v1, but it SHALL still require the pushed subject identity and target reference rather than only a success flag.

#### Scenario: Publish profile required fields
- **WHEN** a chain is evaluated under the `publish` profile
- **THEN** the required fields SHALL include `pushed_subject_digest`, `target_ref`, and `publish_status`

#### Scenario: Bare success flag is insufficient
- **WHEN** a publish flow records success without a stable pushed subject identity or target reference
- **THEN** the `publish` profile verdict SHALL be `failed`

### Requirement: Launch profile uses `launch_id` as the v1 attempt boundary
The `launch` verification profile SHALL treat the existing `launch_id` as the authoritative v1 launch-attempt identity. The verifier SHALL evaluate the latest launch-related event set for the workload using that `launch_id` boundary.

#### Scenario: Latest launch attempt selected by launch_id
- **WHEN** a workload chain contains multiple launch attempts
- **THEN** launch verification SHALL select the latest `launch_id` present in the workload chain and SHALL evaluate only the launch-related events attributed to that identifier

#### Scenario: No separate attempt identifier required in v1
- **WHEN** launch verification is performed in v1
- **THEN** the verifier SHALL NOT require a distinct `launch_attempt_id` if `launch_id` is present and used as the attempt boundary

### Requirement: Launch profile requires both configuration digest and security projection
The `launch` verification profile SHALL require a stable launch configuration digest and explicit security-relevant configuration fields so launch risk can be audited by both machines and humans.

#### Scenario: Launch profile required fields
- **WHEN** a chain is evaluated under the `launch` profile
- **THEN** the required fields SHALL include `launch_id`, `workload_id`, `image_digest`, `launch_config_digest`, `privileged`, `network_mode`, `mounts`, `devices`, and `capabilities`

#### Scenario: Missing launch configuration digest fails
- **WHEN** a launch flow reports success but omits `launch_config_digest`
- **THEN** the `launch` profile verdict SHALL be `failed`

#### Scenario: Missing non-critical environment projection warns
- **WHEN** a launch flow includes the required launch identities and security projection but omits optional non-critical environment metadata
- **THEN** the `launch` profile verdict SHALL be `warning`

### Requirement: Runtime identity requirements are conditional and explicit
The launch and docktap-runtime profiles SHALL distinguish always-required workload identity from conditionally required instance identity.

#### Scenario: Workload identity always required for launch verification
- **WHEN** launch verification is performed for a workload-scoped flow
- **THEN** omission of `workload_id` SHALL produce a `failed` verdict

#### Scenario: Instance identity required after container scope exists
- **WHEN** a launch or runtime event set includes a successful `create`, `start`, `stop`, or `rm` operation for a concrete container
- **THEN** omission of `instance_id` or `container_id` for that container-scoped evidence SHALL produce a `failed` verdict

#### Scenario: Pre-create failure does not require instance identity
- **WHEN** a launch attempt fails before any concrete container instance exists
- **THEN** the absence of `instance_id` SHALL NOT by itself cause the `launch` profile verdict to fail

### Requirement: Docktap runtime profile requires explicit runtime outcomes
The `docktap-runtime` profile SHALL require explicit per-operation outcomes, explicit runtime engine identity, and the minimum identity fields needed to attribute runtime actions to workloads and instances.

#### Scenario: Runtime profile required fields
- **WHEN** a chain is evaluated under the `docktap-runtime` profile for a container-scoped operation
- **THEN** the required fields SHALL include `operation_type`, `operation_result`, `runtime_engine`, `workload_id`, and `instance_id`, and the profile SHALL also require either `image_ref` or `image_digest` when the operation meaning depends on an image target

#### Scenario: Successful runtime operation without audited target fails
- **WHEN** a runtime operation is recorded as successful but omits the workload or instance identity needed to attribute that operation
- **THEN** the `docktap-runtime` profile verdict SHALL be `failed`

### Requirement: Docktap runtime profile SHALL use one mixed-engine contract
The `docktap-runtime` profile SHALL remain one public verification profile across supported runtime engines. The verifier SHALL apply shared engine-agnostic checks first and SHALL then apply any engine-specific checks selected by `runtime_engine`.

#### Scenario: Known engine uses shared and engine-specific checks
- **WHEN** the verifier evaluates a runtime event set whose `runtime_engine` value is recognized
- **THEN** it SHALL evaluate the event set under the single `docktap-runtime` profile using both shared runtime rules and the checks defined for that engine

#### Scenario: Profile name remains stable across engines
- **WHEN** operators evaluate Docker-backed and future non-Docker-backed runtime evidence
- **THEN** the verifier SHALL report both under the same `docktap-runtime` profile rather than splitting them into separate public profile names

### Requirement: Docktap runtime profile SHALL distinguish missing versus unknown engine identity
The verifier SHALL treat missing `runtime_engine` as a producer contract failure and unknown-but-present `runtime_engine` values as incomplete evaluation rather than semantic evidence failure.

#### Scenario: Missing engine identity fails the profile
- **WHEN** a runtime event subject to `docktap-runtime` evaluation omits `runtime_engine`
- **THEN** the `docktap-runtime` profile verdict SHALL be `failed`

#### Scenario: Unknown engine identity yields incomplete evaluation
- **WHEN** a runtime event subject to `docktap-runtime` evaluation includes `runtime_engine` but the verifier does not support engine-specific evaluation for that value
- **THEN** the `docktap-runtime` profile verdict SHALL be `incomplete` rather than `failed`

### Requirement: Profile verdict states are shared across flows
All verification profiles SHALL use the same bounded set of verdict states: `verified`, `warning`, `incomplete`, and `failed`.

#### Scenario: Warning-only omission
- **WHEN** a profile satisfies all hard requirements but omits one or more fields marked warning-only by that profile
- **THEN** the verifier SHALL report the profile verdict as `warning`

#### Scenario: Incomplete evidence
- **WHEN** a profile cannot be fully evaluated because the required event set is not yet complete or confirmed
- **THEN** the verifier SHALL report the profile verdict as `incomplete`

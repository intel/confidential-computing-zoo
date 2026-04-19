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

### Requirement: Signing uses shared OIDC credentials
Docktap SHALL use the same OIDC credential acquisition mechanism as tc_api (`sigstore.oidc.detect_credential()`) to sign DSSE bundles. The OIDC token SHALL be acquired fresh on each commit call. The DSSE predicate format, entry digest computation, and event digest computation SHALL be identical to tc_api's existing signing path.

#### Scenario: DSSE bundle format matches tc_api
- **WHEN** Docktap constructs a DSSE bundle for a Docker operation
- **THEN** the bundle uses predicate type `https://trusted-log.dev/v1`, two-level SHA-384 digest computation, and Sigstore offline signing — identical to tc_api's `TrustedLogAPI.commit_record()`

### Requirement: Best-effort submission semantics
TruCon submission failures SHALL NOT block or delay Docker API responses. Docktap SHALL return the Docker daemon response to the CLI before any retry processing begins. If the initial TruCon commit attempt fails due to a transient transport or server-side error, Docktap SHALL enqueue the submission for bounded asynchronous retry using the same logical commit intent and idempotency key until TruCon acknowledges the `/commit` request or the retry policy is exhausted. Acknowledgement SHALL mean a successful TruCon `/commit` response accepting the event into TruCon's queue; immutable-backend confirmation is out of scope for Docktap. If retry attempts are exhausted, Docktap SHALL mark the submission as terminally failed in its local retry state and log the failure for operators, without retroactively failing the already-completed Docker API response.

#### Scenario: Transient TruCon failure is retried after response
- **WHEN** Docktap has already returned a successful Docker response to the CLI and the initial `POST /commit` attempt fails with a transient network or HTTP 5xx error
- **THEN** Docktap SHALL record a retryable local submission item and retry it asynchronously according to a bounded retry policy

#### Scenario: Retry reuses the original commit intent
- **WHEN** Docktap retries a previously failed submission
- **THEN** it SHALL reuse the same event payload identity and idempotency key so repeated `/commit` attempts represent one logical TruCon commit

#### Scenario: TruCon acknowledgement ends Docktap retry responsibility
- **WHEN** a retry attempt receives a successful TruCon `/commit` response with accepted commit metadata
- **THEN** Docktap SHALL mark the submission as acknowledged and SHALL stop retrying it

#### Scenario: Terminal retry exhaustion does not change Docker CLI result
- **WHEN** a submission reaches the maximum retry limit without receiving TruCon acknowledgement
- **THEN** Docktap SHALL mark the submission as terminally failed and log the failure context
- **THEN** the previously returned Docker CLI response SHALL remain unaffected

#### Scenario: Non-blocking proxy behavior is preserved
- **WHEN** Docktap intercepts a Docker lifecycle request and the associated TruCon submission enters retry handling
- **THEN** Docker response latency SHALL remain decoupled from retry completion and immutable-backend confirmation

### Requirement: Submission occurs after Docker response
Docktap SHALL return the Docker daemon response to the CLI before attempting the TruCon commit. The commit call SHALL occur after response streaming is complete and after the operation record is enriched from the response.

#### Scenario: Response returned before commit
- **WHEN** Docktap intercepts a `create` operation
- **THEN** the Docker response (including container ID) is fully streamed back to the CLI before the TruCon commit HTTP call begins

### Requirement: Cross-source sequence ordering
Events submitted by Docktap and events submitted by tc_api REST workers on the same chain SHALL receive monotonically increasing `sequence_num` values from TruCon's serialized commit path.

#### Scenario: Interleaved Docktap and REST commits on workload chain
- **WHEN** Docktap submits a `start` event and a REST worker submits a `build` event concurrently on the same `chain_id` (e.g., `"my-app"`)
- **THEN** both events receive distinct `sequence_num` values and the sequence is strictly monotonic with no gaps

#### Scenario: Events on different chains are independently sequenced
- **WHEN** Docktap submits events to `chain_id="my-app"` and `chain_id="default"` concurrently
- **THEN** each chain maintains its own independent monotonic `sequence_num` sequence

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

*** Add File: /home/siyuan/tc_api/openspec/specs/verification-profiles/spec.md
## ADDED Requirements

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
The `docktap-runtime` profile SHALL require explicit per-operation outcomes and the minimum identity fields needed to attribute runtime actions to workloads and instances.

#### Scenario: Runtime profile required fields
- **WHEN** a chain is evaluated under the `docktap-runtime` profile for a container-scoped operation
- **THEN** the required fields SHALL include `operation_type`, `operation_result`, `workload_id`, and `instance_id`, and the profile SHALL also require either `image_ref` or `image_digest` when the operation meaning depends on an image target

#### Scenario: Successful runtime operation without audited target fails
- **WHEN** a runtime operation is recorded as successful but omits the workload or instance identity needed to attribute that operation
- **THEN** the `docktap-runtime` profile verdict SHALL be `failed`

### Requirement: Profile verdict states are shared across flows
All verification profiles SHALL use the same bounded set of verdict states: `verified`, `warning`, `incomplete`, and `failed`.

#### Scenario: Warning-only omission
- **WHEN** a profile satisfies all hard requirements but omits one or more fields marked warning-only by that profile
- **THEN** the verifier SHALL report the profile verdict as `warning`

#### Scenario: Incomplete evidence
- **WHEN** a profile cannot be fully evaluated because the required event set is not yet complete or confirmed
- **THEN** the verifier SHALL report the profile verdict as `incomplete`

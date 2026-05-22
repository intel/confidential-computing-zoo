## MODIFIED Requirements

### Requirement: Docktap runtime profile requires explicit runtime outcomes
The `docktap-runtime` profile SHALL require explicit per-operation outcomes, explicit runtime engine identity, and the minimum identity fields needed to attribute runtime actions to workloads and instances.

#### Scenario: Runtime profile required fields
- **WHEN** a chain is evaluated under the `docktap-runtime` profile for a container-scoped operation
- **THEN** the required fields SHALL include `operation_type`, `operation_result`, `runtime_engine`, `workload_id`, and `instance_id`, and the profile SHALL also require either `image_ref` or `image_digest` when the operation meaning depends on an image target

#### Scenario: Successful runtime operation without audited target fails
- **WHEN** a runtime operation is recorded as successful but omits the workload or instance identity needed to attribute that operation
- **THEN** the `docktap-runtime` profile verdict SHALL be `failed`

## ADDED Requirements

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

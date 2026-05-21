## ADDED Requirements

### Requirement: Docktap authorization readiness surface
The system SHALL expose a high-level Docktap authorization readiness capability that external callers can use before Docker-backed work begins. The readiness capability SHALL represent authorization state for a target chain without requiring callers to treat raw delegation creation as the primary integration concept.

#### Scenario: Caller checks authorization before Docker-backed work
- **WHEN** an agent skill, wrapper, or fixed-code launch path requests Docktap authorization readiness for a target chain
- **THEN** the system SHALL return whether authorization is ready for Docker-backed work on that chain

#### Scenario: Readiness remains authorization-scoped
- **WHEN** a caller requests Docktap authorization readiness
- **THEN** the system SHALL evaluate Docktap authorization state and SHALL NOT require the caller to interpret full Docker daemon or registry health as part of that readiness contract

### Requirement: Readiness flow is idempotent and reusable
The system SHALL provide a readiness flow that can reuse an existing active delegation when it already satisfies policy for the target chain, or create delegation when required, and return a stable readiness summary to the caller.

#### Scenario: Existing authorization satisfies readiness
- **WHEN** a caller requests readiness for a chain that already has an active delegation satisfying the current service policy
- **THEN** the system SHALL report authorization as ready without requiring the caller to create a second delegation first

#### Scenario: Missing authorization is created through readiness flow
- **WHEN** a caller requests readiness for a chain that does not have an active delegation satisfying the current service policy
- **THEN** the system SHALL create or complete the required authorization path before reporting readiness success

### Requirement: Readiness summary is stable for agent and non-agent callers
The readiness capability SHALL return a stable summary that callers can consume without needing to understand raw delegation internals. The summary SHALL identify the target chain, whether authorization is ready, the effective scope, and the authorization expiry when readiness is satisfied.

#### Scenario: Agent skill consumes readiness summary
- **WHEN** an agent-oriented caller uses the readiness capability
- **THEN** the returned summary SHALL contain enough information for the caller to continue Docker-backed work without separately querying raw delegation state

#### Scenario: Non-agent wrapper consumes readiness summary
- **WHEN** a non-agent script or wrapper uses the readiness capability
- **THEN** the returned summary SHALL contain enough information for the wrapper to decide whether to launch the workload or surface the next required operator action

### Requirement: Runtime challenge remains available as fallback
The system SHALL preserve Docktap runtime authorization challenge behavior when callers do not use the readiness flow or arrive through older paths.

#### Scenario: Caller skips preflight readiness
- **WHEN** a caller starts Docker-backed work without first ensuring Docktap authorization readiness and the required authorization is absent
- **THEN** Docktap SHALL continue to block the runtime operation and return an authorization challenge response

#### Scenario: Readiness path becomes preferred but not mandatory for compatibility
- **WHEN** callers still rely on older runtime-triggered authorization flows
- **THEN** the system SHALL preserve enforcement and recovery behavior through Docktap challenge handling
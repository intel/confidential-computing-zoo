## ADDED Requirements

### Requirement: Docktap SHALL normalize auditable lifecycle operations behind a runtime-engine boundary
Docktap SHALL provide a runtime-engine abstraction that converts engine-specific request and response handling into one canonical auditable lifecycle model for `pull`, `create`, `start`, `stop`, and `rm`.

#### Scenario: Docker traffic maps to canonical lifecycle operations
- **WHEN** Docktap processes a Docker runtime request that corresponds to an auditable lifecycle action
- **THEN** the runtime-engine abstraction SHALL classify that request into the canonical operation type used by downstream tracking, commit, and verification logic

#### Scenario: Future Podman traffic maps to the same canonical lifecycle operations
- **WHEN** Docktap processes a future Podman runtime request that corresponds to the same auditable lifecycle action
- **THEN** the runtime-engine abstraction SHALL map it to the same canonical operation type rather than inventing a separate engine-specific lifecycle taxonomy

### Requirement: Docktap SHALL preserve engine-specific parsing inside the adapter boundary
Engine-specific socket paths, request patterns, and metadata extraction SHALL be handled inside the runtime-engine abstraction rather than leaking engine-specific conditionals into downstream commit or verification contracts.

#### Scenario: Downstream runtime commit logic consumes normalized metadata
- **WHEN** Docktap prepares an auditable runtime event after engine-specific request parsing
- **THEN** downstream TruCon commit logic SHALL consume normalized lifecycle metadata without requiring engine-specific request-shape knowledge

#### Scenario: Verifier-facing event semantics remain stable across engines
- **WHEN** Docktap emits auditable runtime events for different supported engines
- **THEN** the verifier-facing lifecycle fields SHALL keep the same meanings across engines and SHALL differ only where explicitly modeled as engine metadata

### Requirement: Docktap SHALL emit explicit engine identity for all auditable runtime events
Every auditable runtime event emitted by Docktap SHALL include a `runtime_engine` field whose value identifies the engine that produced the normalized lifecycle event.

#### Scenario: Docker runtime event includes engine identity
- **WHEN** Docktap emits an auditable runtime event for the existing Docker path
- **THEN** the event SHALL include `runtime_engine="docker"`

#### Scenario: Future non-Docker runtime event includes engine identity
- **WHEN** Docktap emits an auditable runtime event for a future supported non-Docker engine
- **THEN** the event SHALL include the canonical engine identifier for that engine rather than omitting the field

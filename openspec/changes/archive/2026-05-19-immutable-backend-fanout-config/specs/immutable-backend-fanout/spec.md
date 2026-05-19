## ADDED Requirements

### Requirement: TruCon SHALL support immutable backend write-set configuration
TruCon SHALL accept startup configuration that declares one or more enabled immutable write backends as a set rather than a single hard-coded backend selector. The supported configured write-set values in this phase SHALL be `rekor`, `onchain`, and `rekor,onchain`.

#### Scenario: Rekor-only write set
- **WHEN** TruCon starts with immutable write backends configured as `rekor`
- **THEN** TruCon SHALL instantiate only the Rekor immutable adapter for submissions

#### Scenario: On-chain-only write set
- **WHEN** TruCon starts with immutable write backends configured as `onchain`
- **THEN** TruCon SHALL instantiate only the on-chain immutable adapter for submissions

#### Scenario: Dual-backend write set requested
- **WHEN** TruCon starts with immutable write backends configured as `rekor,onchain`
- **THEN** TruCon SHALL evaluate that request as a multi-backend fanout configuration rather than collapsing it to a single backend choice

### Requirement: TruCon SHALL preserve an explicit primary immutable backend
TruCon SHALL keep one configured primary immutable backend for authoritative read-oriented behavior, including the immutable adapter contract exposed to the submit daemon and the backend used by existing traversal and lookup flows.

#### Scenario: Primary backend defaults to Rekor
- **WHEN** TruCon starts without an explicit primary immutable backend override
- **THEN** TruCon SHALL treat `rekor` as the primary immutable backend

#### Scenario: Single-backend mode uses that backend as primary
- **WHEN** TruCon starts with exactly one immutable write backend configured
- **THEN** that backend SHALL also be treated as the primary immutable backend

### Requirement: TruCon SHALL expose a composite immutable adapter for fanout mode
When more than one immutable write backend is configured, TruCon SHALL construct a composite immutable adapter that implements the same `ImmutableLogAdapter` contract while fanning out submissions to the configured backend adapters.

#### Scenario: Fanout mode builds a composite adapter
- **WHEN** TruCon starts with more than one immutable write backend enabled
- **THEN** the immutable adapter passed into the submit daemon SHALL be a composite adapter rather than a raw backend adapter instance

#### Scenario: Composite adapter preserves primary return contract
- **WHEN** the composite immutable adapter submits a bundle successfully
- **THEN** it SHALL return the primary backend's immutable-log identity and receipt in the existing adapter contract exposed to current callers

### Requirement: TruCon SHALL define an explicit immutable write policy
TruCon SHALL define an explicit immutable write policy for multi-backend mode so future backend fanout confirmation behavior is unambiguous, even if this phase still treats the primary backend as authoritative.

#### Scenario: Primary policy is used in phase one
- **WHEN** TruCon runs with more than one immutable write backend configured in this phase
- **THEN** record confirmation semantics SHALL continue to be driven by the primary backend rather than requiring every configured backend to succeed

#### Scenario: Secondary backend outcomes remain observable
- **WHEN** a non-primary immutable backend submission fails during fanout processing
- **THEN** TruCon SHALL surface that backend-specific failure through logging or adapter metadata rather than silently discarding it

### Requirement: Unsupported fanout combinations SHALL fail at startup
TruCon SHALL reject immutable write-set configurations that include an unimplemented backend in a mode that would imply active dual-write behavior.

#### Scenario: Placeholder on-chain blocks `rekor,onchain`
- **WHEN** TruCon starts with immutable write backends configured as `rekor,onchain` while the on-chain adapter remains a placeholder implementation
- **THEN** TruCon SHALL fail startup with a clear configuration error instead of serving traffic in degraded silent mode

#### Scenario: Unknown backend name is rejected
- **WHEN** TruCon starts with an immutable write-set value containing an unsupported backend name
- **THEN** TruCon SHALL fail startup with an error listing the supported backend names
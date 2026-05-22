## ADDED Requirements

### Requirement: Decoupled ImmutableLogAdapter Interface
The system SHALL define a decoupled `ImmutableLogAdapter` interface dictating how to interact with transparent logs, which must include `submit()`, `get()`, and `traverse()` methods.

#### Scenario: Interface extraction and encapsulation
- **WHEN** the transparency log sub-system is initialized
- **THEN** it instantiates an implementation of `ImmutableLogAdapter` (e.g., `SigstoreLogAdapter`) that safely encapsulates all external API calls or subprocess logic away from `api.py`.

#### Scenario: Supporting Sigstore specific implementation
- **WHEN** submitting or fetching a log entry
- **THEN** the system routes the request through `SigstoreLogAdapter` which interacts with Sigstore/Rekor, abstracting away the CLI or HTTP calls.
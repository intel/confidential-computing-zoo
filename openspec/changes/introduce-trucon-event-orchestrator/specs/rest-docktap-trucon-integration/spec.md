## ADDED Requirements

### Requirement: Existing REST control-plane flows SHALL integrate with TruCon without external API breakage
The existing REST API control-plane flows for build, publish, and launch SHALL publish trusted events through TruCon while preserving external endpoint contracts and result semantics.

#### Scenario: Build flow publishes trusted events via TruCon
- **WHEN** build lifecycle steps produce trusted-event evidence
- **THEN** the REST control-plane path sends those events through TruCon APIs and continues returning the existing external response contract

#### Scenario: Publish flow publishes trusted events via TruCon
- **WHEN** publish lifecycle steps produce trusted-event evidence
- **THEN** the REST control-plane path sends those events through TruCon APIs and continues returning the existing external response contract

### Requirement: Docktap service process SHALL report runtime trusted events through TruCon
Docktap as an independent service process SHALL send runtime interception and lifecycle events to TruCon rather than directly mutating trusted-log chain state.

#### Scenario: Docktap process emits runtime event
- **WHEN** Docktap captures a runtime-relevant event for a managed container operation
- **THEN** Docktap submits that event to TruCon using internal API contracts and receives acknowledgement or retry guidance

#### Scenario: Concurrent event sources
- **WHEN** REST workers and Docktap workers concurrently submit events for related workload contexts
- **THEN** TruCon preserves defined ordering and correlation semantics for downstream submission and query behavior

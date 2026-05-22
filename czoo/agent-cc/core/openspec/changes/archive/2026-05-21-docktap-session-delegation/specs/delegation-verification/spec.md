## ADDED Requirements

### Requirement: Delegation-aware signer identity verification
The verification system SHALL support two signer identity modes: (1) Fulcio-signed events with SAN-based identity matching (existing behavior); (2) owner-key-signed events where signer identity is inferred through delegation chain.

#### Scenario: Fulcio-signed event matches policy
- **WHEN** a chain event has a Fulcio certificate with SAN matching the policy's authorized identity
- **THEN** the verifier SHALL mark `signer_identity_match: true`

#### Scenario: Owner-key-signed event validated via delegation
- **WHEN** a chain event has no Fulcio SAN (signer_identity is None) but references a valid delegation_id
- **THEN** the verifier SHALL trace the delegation_id to the corresponding delegation event, verify the delegation event's Fulcio SAN matches policy, and mark the business event as delegation-verified

### Requirement: Delegation chain annotation
The verification system SHALL annotate each chain event with a `delegation_status` field indicating delegation verification status.

#### Scenario: Delegation event itself
- **WHEN** a chain event has `event_type: "session.delegation"` and a valid Fulcio SAN
- **THEN** the verifier SHALL set `delegation_status: "origin"` and record the delegation's scope, expires_at, and delegation_id

#### Scenario: Business event within delegation scope and TTL
- **WHEN** a chain event references a `delegation_id` and the event's timestamp is before the delegation's `expires_at` and the event's operation type is in the delegation's `scope`
- **THEN** the verifier SHALL set `delegation_status: "proven"`

#### Scenario: Business event outside delegation TTL
- **WHEN** a chain event references a `delegation_id` but the event's timestamp exceeds the delegation's `expires_at`
- **THEN** the verifier SHALL set `delegation_status: "expired"` and add an error

#### Scenario: Business event outside delegation scope
- **WHEN** a chain event references a `delegation_id` but the event's operation type is not in the delegation's `scope`
- **THEN** the verifier SHALL set `delegation_status: "scope_violation"` and add an error

#### Scenario: Business event with missing delegation reference
- **WHEN** a chain event has no Fulcio SAN and no `delegation_id` in its predicate
- **THEN** the verifier SHALL set `delegation_status: "missing"` and add an error

### Requirement: Owner verification remains independent
The existing `_annotate_owner_verification` logic SHALL continue to operate independently of delegation verification. Both `owner_status` and `delegation_status` SHALL be present on each event.

#### Scenario: Event has both owner and delegation annotations
- **WHEN** a chain event is verified
- **THEN** the event SHALL have both `owner_status` (from owner key verification) and `delegation_status` (from delegation chain verification) as independent fields

## ADDED Requirements

### Requirement: Attested-head evidence must not replace historical replay proof
The attested-head evidence contract SHALL remain limited to current-head attestation and SHALL NOT become the verifier-facing source of truth for Event Log 0 baseline origin or historical predecessor continuity.

#### Scenario: Evidence validation does not require historical replay fields
- **WHEN** a v1 attested-head evidence package is produced or validated
- **THEN** it SHALL remain valid without embedding Event Log 0 baseline fields, predecessor-chain linkage fields, or other replay-only historical proof data

#### Scenario: Historical proof remains delegated to Rekor replay
- **WHEN** a verifier consumes a valid attested-head evidence package alongside immutable-backend replay
- **THEN** the verifier SHALL continue to derive baseline-origin and predecessor-continuity proof from Rekor-backed replay rather than from the evidence package

### Requirement: Evidence extensions must not blur provenance boundaries
Optional evidence extensions SHALL NOT redefine replay-only historical facts as evidence-backed truths in a way that obscures whether those facts were publicly auditable from Rekor.

#### Scenario: Extension fields remain non-authoritative for replay history
- **WHEN** an attested-head evidence package includes optional extensions or convenience metadata related to historical replay
- **THEN** validators and operator tooling SHALL treat those fields as supplementary metadata and SHALL NOT use them to satisfy required public replay proof obligations

#### Scenario: Current-head binding remains the only trust-critical evidence contract
- **WHEN** operator tooling reports the result of evidence-backed verification
- **THEN** the trust-critical meaning of the evidence package SHALL remain the quote-backed binding of the current public head rather than historical chain reconstruction
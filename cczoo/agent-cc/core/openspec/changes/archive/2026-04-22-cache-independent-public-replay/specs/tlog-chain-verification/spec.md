## ADDED Requirements

### Requirement: Public replay proof facts must be Rekor-auditable
Immutable-backend replay SHALL treat verifier-critical historical facts as proven only when they can be materialized from Rekor-auditable entry data. Process-local bundle cache MAY be used as a fetch optimization, but cache-only facts SHALL NOT be treated as proof truth for Event Log 0 baseline origin, signed predecessor continuity, or signer-linked replay identity.

#### Scenario: Cache-cleared replay still proves historical continuity
- **WHEN** immutable-backend replay verifies a public Rekor chain after process-local bundle cache has been cleared or when replay runs in a fresh verifier process
- **THEN** the replay result SHALL prove Event Log 0 origin and signed predecessor continuity only from Rekor-materialized entries and related public candidate discovery data

#### Scenario: Cache-only historical facts do not upgrade replay to verified
- **WHEN** the verifier can recover a historical fact only from process-local bundle-derived cache state and not from Rekor-auditable materialization
- **THEN** the replay result SHALL remain degraded, unsupported, or failed for that proof dimension rather than reporting the fact as publicly verified history

#### Scenario: Cache disagreement is resolved in favor of public materialization
- **WHEN** process-local cache content disagrees with Rekor-materialized replay facts for the same immutable entry
- **THEN** immutable-backend verification SHALL treat Rekor-materialized data as authoritative for replay proof and SHALL surface the disagreement as a diagnostic rather than silently trusting cached reconstruction

### Requirement: Event Log 0 baseline origin must remain publicly replayable
For chains that require Event Log 0, immutable-backend replay SHALL recover the baseline-origin facts needed for external verification from Rekor-auditable replay material rather than from exported evidence or process-local cache-only reconstruction.

#### Scenario: Workload chain baseline is recovered from public replay
- **WHEN** immutable-backend replay verifies a non-`default` chain that begins with Event Log 0
- **THEN** the verifier SHALL derive the required baseline-origin facts for that chain from the replayed immutable entries themselves rather than from the attested-head evidence package

#### Scenario: Missing public baseline facts prevent public verification
- **WHEN** a verifier cannot recover the required Event Log 0 baseline-origin facts from Rekor-auditable replay material
- **THEN** immutable-backend verification SHALL report that public baseline proof is unavailable rather than silently substituting local cache or evidence-package data
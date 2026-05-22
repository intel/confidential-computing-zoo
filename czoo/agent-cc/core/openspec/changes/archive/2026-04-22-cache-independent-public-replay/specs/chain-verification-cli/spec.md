## ADDED Requirements

### Requirement: CLI reports provenance split between public replay and exported evidence
The chain verification CLI SHALL expose the verifier's provenance boundary so operators can distinguish publicly auditable replay facts from current-head facts that are bound by exported attested evidence.

#### Scenario: JSON output preserves verification provenance
- **WHEN** the CLI produces JSON output for evidence-backed verification
- **THEN** the normalized result SHALL preserve machine-readable indication of which successful verification dimensions came from public immutable replay and which came from exported attested-head evidence

#### Scenario: Human-readable output explains verifier trust sources
- **WHEN** the CLI produces default terminal output for evidence-backed verification
- **THEN** the output SHALL explain that historical continuity and baseline origin come from public replay while current-head endorsement comes from exported evidence

### Requirement: CLI does not overstate cache-assisted historical proof
The chain verification CLI SHALL NOT render historical replay as publicly verified when the underlying verifier result depends on cache-only reconstruction rather than Rekor-auditable materialization.

#### Scenario: Unsupported cache-assisted replay is surfaced to operators
- **WHEN** immutable-backend replay succeeds only because process-local cache provides historical facts that are not recoverable from Rekor-auditable materialization
- **THEN** the CLI SHALL report that replay as degraded, unsupported, or failed for public audit purposes rather than presenting it as fully verified public history

#### Scenario: Evidence success does not hide replay provenance failure
- **WHEN** exported attested-head evidence validates successfully but public replay cannot establish the required historical proof boundary
- **THEN** the CLI SHALL preserve the successful current-head attestation result while separately reporting the replay provenance deficiency rather than collapsing the outcome into an unqualified overall success
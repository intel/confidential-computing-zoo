## ADDED Requirements

### Requirement: Immutable replay can materialize predecessor bundles from a mirror
`TrustedLogAPI.verify_record()` SHALL support mirror-backed predecessor materialization for newly written replayable nodes when public immutable-log entry data does not contain enough payload material to reconstruct a replayable predecessor entry on its own.

#### Scenario: Mirror-backed materialization proves predecessor continuity
- **WHEN** replay verification cannot recover a replayable predecessor payload from public immutable-log entry data alone but a configured mirror resolves a `bundle.json` for the required `payload_hash`
- **THEN** the verifier SHALL normalize the mirrored bundle into replayable predecessor facts and SHALL evaluate signed predecessor continuity against that normalized material

#### Scenario: Mirror-required policy rejects missing mirrored content
- **WHEN** replay verification runs with a mirror-required policy and the required mirrored bundle cannot be resolved for a `payload_hash`
- **THEN** the verifier SHALL report predecessor proof as incomplete, degraded, or failed according to structured policy output rather than silently falling back to cache-only reconstruction

### Requirement: Immutable replay reports materialization provenance
`TrustedLogAPI.verify_record()` SHALL preserve machine-readable provenance that distinguishes public immutable-log materialization from mirror-backed materialization when replay verification reports historical continuity results.

#### Scenario: Structured replay result marks mirrored materialization
- **WHEN** replay verification succeeds using a mirrored predecessor bundle
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from the mirror rather than from public immutable-log entry data alone

#### Scenario: Structured replay result preserves public-only state
- **WHEN** replay verification reaches the requested head without using mirrored bundle material
- **THEN** the structured immutable-backend result SHALL preserve that replay state as public-only rather than conflating it with mirrored replay success
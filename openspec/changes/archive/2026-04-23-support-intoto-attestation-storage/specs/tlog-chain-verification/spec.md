## MODIFIED Requirements

### Requirement: Immutable replay can materialize predecessor bundles from a mirror
`TrustedLogAPI.verify_record()` SHALL support mirror-backed predecessor materialization for newly written replayable nodes when public immutable-log entry data and Rekor attestation storage do not contain enough payload material to reconstruct a replayable predecessor entry on their own.

#### Scenario: Mirror-backed materialization proves predecessor continuity
- **WHEN** replay verification cannot recover a replayable predecessor payload from public immutable-log entry data or Rekor attestation storage alone but a configured mirror resolves a `bundle.json` for the required `payload_hash`
- **THEN** the verifier SHALL normalize the mirrored bundle into replayable predecessor facts and SHALL evaluate signed predecessor continuity against that normalized material

#### Scenario: Mirror-required policy rejects missing mirrored content
- **WHEN** replay verification runs with a mirror-required policy and the required mirrored bundle cannot be resolved for a `payload_hash`
- **THEN** the verifier SHALL report predecessor proof as incomplete, degraded, or failed according to structured policy output rather than silently falling back to cache-only reconstruction

### Requirement: Immutable replay reports materialization provenance
`TrustedLogAPI.verify_record()` SHALL preserve machine-readable provenance that distinguishes public immutable-log materialization, Rekor attestation-storage materialization, and mirror-backed materialization when replay verification reports historical continuity results.

#### Scenario: Structured replay result marks mirrored materialization
- **WHEN** replay verification succeeds using a mirrored predecessor bundle
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from the mirror rather than from public immutable-log entry data alone

#### Scenario: Structured replay result marks attestation-storage materialization
- **WHEN** replay verification succeeds using payload material recovered from Rekor attestation storage
- **THEN** the structured immutable-backend result SHALL indicate that the relevant historical proof dimension was materialized from `attestation-storage` rather than from public body fields or OCI mirror

#### Scenario: Structured replay result preserves public-only state
- **WHEN** replay verification reaches the requested head without using mirrored bundle material or attestation-storage materialization
- **THEN** the structured immutable-backend result SHALL preserve that replay state as public-only rather than conflating it with mirrored or attestation-backed replay success

## ADDED Requirements

### Requirement: Immutable replay materializes payload facts from Rekor attestation storage
`TrustedLogAPI.verify_record()` SHALL materialize replayable payload facts from Rekor attestation storage when the public immutable-log body is not sufficient on its own.

#### Scenario: Attestation-backed candidate is normalized for predecessor verification
- **WHEN** predecessor candidate discovery returns a Rekor entry whose public body is hash-only but whose retrieval response contains attestation material that matches the entry's committed payload hash
- **THEN** immutable replay SHALL normalize that attestation into replayable predecessor facts and SHALL include the candidate in signed predecessor verification

#### Scenario: Invalid attestation material is rejected
- **WHEN** a retrieved attestation payload does not match the committed payload hash recorded by the immutable-log entry
- **THEN** immutable replay SHALL reject that attestation material for proof purposes and SHALL continue with remaining valid candidates or report failure if none remain
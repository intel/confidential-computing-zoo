## MODIFIED Requirements

### Requirement: CLI reports verification tiers for public, mirrored, and attested results
The chain verification CLI SHALL distinguish `public-only`, `public+attestation-storage`, `public+mirrored`, and `public+mirrored+attested` verification outcomes in both JSON and human-readable output.

#### Scenario: JSON output preserves verification tier
- **WHEN** the CLI produces JSON output for a verification run that combines immutable replay, Rekor attestation-storage materialization, mirrored bundle materialization, or attested-head evidence
- **THEN** the normalized result SHALL include a machine-readable verification tier that distinguishes whether the run was public-only, public+attestation-storage, public+mirrored, or public+mirrored+attested

#### Scenario: Human-readable output explains attestation-storage versus mirrored success
- **WHEN** the CLI produces terminal output for a verification run that uses Rekor attestation-storage materialization or mirrored bundle materialization
- **THEN** the summary SHALL explain whether historical continuity came from public-only replay, required attestation-storage materialization, mirrored materialization, or mirrored replay plus current-head attestation

### Requirement: CLI applies mirror policy explicitly
The chain verification CLI SHALL apply mirror configuration through verifier policy or verification profiles and SHALL preserve the result of mirror-required versus mirror-optional verification runs.

#### Scenario: Mirror-optional verification remains attestation-backed when mirror is absent
- **WHEN** the CLI runs with mirror-optional policy, OCI mirror content is absent, and required historical payload material is available from Rekor attestation storage
- **THEN** the CLI SHALL preserve the run as attestation-storage-backed verification rather than downgrading it to mirrored or failed output

#### Scenario: Mirror-optional verification remains public-only when no materialization source is needed
- **WHEN** the CLI runs with mirror-optional policy and the public immutable-log body already contains sufficient replayable material
- **THEN** the CLI SHALL preserve the run as public-only rather than inflating it to attestation-storage or mirrored success

## ADDED Requirements

### Requirement: CLI reports attestation-storage provenance explicitly
The chain verification CLI SHALL expose Rekor attestation-storage materialization as a distinct provenance source in both JSON diagnostics and human-readable summaries.

#### Scenario: JSON output preserves attestation-storage provenance
- **WHEN** the CLI produces JSON output for a replay that used Rekor attestation storage to materialize verifier-critical payload facts
- **THEN** the normalized result SHALL preserve a machine-readable provenance value of `attestation-storage` for the relevant historical proof dimension

#### Scenario: Human-readable output explains Rekor-hosted materialization
- **WHEN** the CLI produces default terminal output for a verification run that used Rekor attestation storage
- **THEN** the output SHALL explain that historical continuity depended on Rekor-hosted attestation material rather than OCI mirror fallback
## ADDED Requirements

### Requirement: CLI reports verification tiers for public, mirrored, and attested results
The chain verification CLI SHALL distinguish `public-only`, `public+mirrored`, and `public+mirrored+attested` verification outcomes in both JSON and human-readable output.

#### Scenario: JSON output preserves verification tier
- **WHEN** the CLI produces JSON output for a verification run that combines immutable replay, mirrored bundle materialization, or attested-head evidence
- **THEN** the normalized result SHALL include a machine-readable verification tier that distinguishes whether the run was public-only, public+mirrored, or public+mirrored+attested

#### Scenario: Human-readable output explains mirrored versus attested success
- **WHEN** the CLI produces terminal output for a verification run that uses mirrored bundle materialization or attested-head evidence
- **THEN** the summary SHALL explain whether historical continuity came from public-only replay, required mirrored materialization, or mirrored replay plus current-head attestation

### Requirement: CLI applies mirror policy explicitly
The chain verification CLI SHALL apply mirror configuration through verifier policy or verification profiles and SHALL preserve the result of mirror-required versus mirror-optional verification runs.

#### Scenario: Mirror-optional verification remains public-only when mirror is absent
- **WHEN** the CLI runs with mirror-optional policy and required mirrored bundle material is absent or delayed
- **THEN** the CLI SHALL preserve the run as public-only or degraded according to immutable replay results rather than presenting it as mirrored success

#### Scenario: Mirror-required verification reports missing mirror material
- **WHEN** the CLI runs with mirror-required policy and a required mirrored bundle cannot be resolved
- **THEN** the CLI SHALL fail or degrade the verification run with explicit mirror-materialization diagnostics rather than collapsing the issue into a generic replay error
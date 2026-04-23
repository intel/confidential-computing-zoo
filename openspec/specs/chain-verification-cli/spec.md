## Purpose

Define the operator-facing verification requirements for the chain verification CLI, including replay, evidence handling, troubleshooting behavior, and result reporting.
## Requirements
### Requirement: CLI requires Event Log 0 for non-default chains
The chain verification CLI SHALL require every non-`default` chain to begin with Event Log 0 in both evidence-backed replay mode and explicit live troubleshooting mode.

#### Scenario: Evidence-backed verification of workload chain with baseline
- **WHEN** `tc-verify` replays a non-`default` chain from immutable-backend evidence and the first replayed record is Event Log 0
- **THEN** the CLI SHALL continue verification normally and SHALL evaluate replay, attested-head, and profile results on that chain

#### Scenario: Evidence-backed verification fails for workload chain without baseline
- **WHEN** `tc-verify` replays a non-`default` chain whose first replayed record is not Event Log 0
- **THEN** the CLI SHALL fail verification and SHALL report the missing baseline as a structural chain-origin error

#### Scenario: Live troubleshooting verification also rejects missing baseline
- **WHEN** `tc-verify` runs in explicit live troubleshooting mode for a non-`default` chain whose first record is not Event Log 0
- **THEN** the CLI SHALL report the chain as failed rather than downgrading the issue to a warning or incomplete state

### Requirement: CLI reports profile-scoped verification verdicts
The chain verification CLI SHALL evaluate and report profile-scoped verdicts for `build`, `publish`, `launch`, and `docktap-runtime` separately from structural replay and evidence results.

#### Scenario: Profile verdicts included in JSON output
- **WHEN** an operator invokes the CLI with `--json`
- **THEN** the normalized result SHALL include a dedicated profile-verdict section that reports the verdict, matched evidence set, and profile-specific findings for each evaluated profile

#### Scenario: Profile verdicts separated from replay status
- **WHEN** immutable-backend replay succeeds but one or more profiles fail their application-layer checks
- **THEN** the CLI SHALL preserve replay success while reporting the failing profiles independently rather than collapsing everything into one undifferentiated status

### Requirement: CLI evaluates the latest launch attempt by `launch_id`
The chain verification CLI SHALL evaluate the launch profile against the latest workload-scoped launch attempt identified by `launch_id`.

#### Scenario: Latest launch_id selected
- **WHEN** the workload chain contains more than one launch-related event set
- **THEN** the CLI SHALL determine the latest `launch_id` present in the workload chain and SHALL restrict launch-profile evaluation to the event set attributed to that identifier

#### Scenario: Pre-create launch failure remains attributable
- **WHEN** the latest launch attempt fails before a container instance is created
- **THEN** the CLI SHALL still evaluate and report that launch attempt by `launch_id` rather than skipping launch verification due to missing `instance_id`

### Requirement: CLI distinguishes hard failures, warnings, and incomplete profile evidence
The chain verification CLI SHALL distinguish profile hard failures, warning-only omissions, and incomplete evidence in both text and JSON output.

#### Scenario: Warning profile result
- **WHEN** a profile satisfies all hard requirements but omits warning-only metadata
- **THEN** the CLI SHALL report that profile as `warning` and SHALL enumerate the warning findings separately from hard failures

#### Scenario: Incomplete profile result
- **WHEN** a profile cannot be fully evaluated because the event set is pending, truncated, or otherwise incomplete
- **THEN** the CLI SHALL report that profile as `incomplete` and SHALL identify which required evidence was missing

### Requirement: Package verification CLI entry point
The system SHALL expose a package-level chain verification CLI command for operators and auditors.

#### Scenario: Console script is installed
- **WHEN** the package is installed in a supported environment
- **THEN** a console command for chain verification SHALL be available without invoking a repository-local helper script

#### Scenario: CLI uses package configuration
- **WHEN** the CLI starts verification
- **THEN** it SHALL use the package's configured runtime settings and shared verification code paths rather than maintaining an independent script-only configuration path

### Requirement: Evidence-backed verification input mode
The CLI SHALL treat a valid v1 attested-head evidence package as the supported external operator input for verification and SHALL derive replay targets from that package.

#### Scenario: Verify from exported evidence
- **WHEN** an operator invokes the CLI with a valid v1 attested-head evidence package
- **THEN** the CLI SHALL derive `chain_id`, `head_log_id`, `sequence_num`, and `mr_value` from that package instead of requiring live TruCon discovery calls

#### Scenario: Invalid evidence package rejected
- **WHEN** an operator invokes the CLI with a package that fails the shared attested-head evidence validation rules
- **THEN** the CLI SHALL fail verification and SHALL report the evidence package as invalid before attempting immutable-backend replay

#### Scenario: External verification without evidence is rejected
- **WHEN** an operator invokes the CLI without an evidence package and without explicitly selecting troubleshooting mode
- **THEN** the CLI SHALL fail fast and SHALL instruct the caller to use exported evidence for supported external verification

### Requirement: Replay must reach the attested head described by evidence
The CLI SHALL verify that immutable-backend replay reaches the same chain head described by the attested-head evidence package.

#### Scenario: Evidence head matches replayed head
- **WHEN** immutable-backend replay reaches a head whose `chain_id`, `sequence_num`, `head_log_id`, and `mr_value` match the attested-head evidence package
- **THEN** the CLI SHALL report the replay-to-evidence association as successful

#### Scenario: Evidence head does not match replayed head
- **WHEN** immutable-backend replay does not reach the `chain_id`, `sequence_num`, `head_log_id`, or `mr_value` described by the attested-head evidence package
- **THEN** the CLI SHALL fail verification and SHALL report which association field did not match

### Requirement: Live TruCon mode is retained only as explicit troubleshooting mode
The CLI SHALL allow live TruCon-backed verification only when the caller explicitly selects a troubleshooting-oriented mode, and it SHALL not present that mode as a supported external verifier contract.

#### Scenario: Troubleshooting mode invocation is explicit
- **WHEN** an operator invokes the CLI with a live `chain_id` selector
- **THEN** the CLI SHALL require an explicit troubleshooting selector rather than silently treating the request as normal external verification

#### Scenario: Troubleshooting mode is labeled as internal
- **WHEN** the CLI runs in live TruCon-backed troubleshooting mode
- **THEN** help text, diagnostics, and final result reporting SHALL identify that run as troubleshooting or internal mode rather than as the preferred verifier contract

#### Scenario: Evidence-backed invocation avoids live TruCon dependency
- **WHEN** an operator invokes the CLI with an evidence package
- **THEN** the CLI SHALL complete without requiring successful live TruCon connectivity for chain-state discovery or local verification

### Requirement: `chain_id` is not a standalone external verification target in v1
The CLI SHALL accept a v1 attested-head evidence package as the supported external verification target in v1, and it MAY accept a `chain_id` only when troubleshooting mode is explicitly requested.

#### Scenario: Bare chain_id invocation is not treated as external verification
- **WHEN** an operator invokes the CLI with a `chain_id` but without explicit troubleshooting mode
- **THEN** the CLI SHALL reject the invocation instead of silently reinterpreting it as a supported external verifier path

#### Scenario: Verify a chain by evidence package
- **WHEN** an operator invokes the CLI with a v1 attested-head evidence package
- **THEN** the CLI SHALL treat the package as the verification target source and SHALL NOT require any alternate selector to resolve the attested head

### Requirement: Dual-source verification aggregation
The CLI SHALL treat immutable-backend replay and attested-head evidence validation as the supported external verification sources, while any live TruCon verification that remains available SHALL be surfaced only as explicitly requested troubleshooting data.

#### Scenario: Evidence-backed verification succeeds
- **WHEN** immutable-backend replay succeeds and the attested-head evidence package is valid and matches the replayed head
- **THEN** the CLI SHALL report successful replay and attested-head outcomes in the normalized result and SHALL render a successful overall summary without requiring live TruCon success

#### Scenario: Troubleshooting source is unavailable
- **WHEN** the CLI runs in explicit troubleshooting mode and the TruCon source is unavailable or errors
- **THEN** the CLI SHALL preserve that failed troubleshooting outcome in the normalized result while still identifying the mode as internal diagnostics rather than normal external verification

### Requirement: Stable JSON result model
The CLI SHALL support a stable JSON output mode that distinguishes immutable replay findings from attested-head evidence findings and from explicit live troubleshooting findings. For reservation-backed replayable records, the replay result model SHALL expose signed predecessor-continuity findings rather than backend-specific `prev_log_id` linkage status, and SHALL preserve the machine-readable predecessor vocabulary emitted by immutable replay and TruCon verification.

#### Scenario: JSON output requested
- **WHEN** the CLI is invoked with `--json`
- **THEN** the output SHALL include top-level sections for `target`, `mode`, `summary`, `replay`, `attested_head`, and `errors`, and it MAY include an additional troubleshooting section when live TruCon verification is explicitly used

#### Scenario: JSON output includes per-record replay detail
- **WHEN** JSON output is produced for a chain with one or more replayed records
- **THEN** the replay portion of the normalized result SHALL include record-level identifiers and verification detail sufficient to diagnose immutable-backend predecessor failures independently from attested-head failures

#### Scenario: JSON output preserves predecessor pipeline detail
- **WHEN** a replayed record includes reservation-backed predecessor verification detail
- **THEN** the CLI JSON output SHALL preserve `predecessor_ok`, `predecessor_status`, and any available candidate-pipeline counts rather than reducing them to text-only diagnostics

#### Scenario: JSON output preserves replay boundary classification
- **WHEN** replay verification encounters a boundary between predecessor-proof regimes
- **THEN** the JSON result SHALL preserve a machine-readable `boundary_status` or equivalent replay-regime classification rather than forcing operators to infer that state from free-form error text

### Requirement: CLI reports signed predecessor continuity findings
The chain verification CLI SHALL render signed predecessor verification results in both JSON and human-readable output so operators can distinguish candidate-discovery failures from signed continuity mismatches, decode failures from no-match outcomes, and degraded replay from invalid replay.

#### Scenario: JSON output reports predecessor status
- **WHEN** a replayed record includes reservation-backed predecessor verification detail
- **THEN** the CLI JSON output SHALL expose `predecessor_status` in addition to `predecessor_ok` and associated candidate-discovery diagnostics for that record

#### Scenario: Human-readable output reports predecessor failure source
- **WHEN** replay verification fails because predecessor lookup returned no matching signed candidate, because candidate discovery failed, because discovered candidates could not be decoded into replayable entries, or because more than one candidate matched the signed predecessor contract
- **THEN** the default terminal output SHALL identify predecessor continuity as the failing replay dimension and SHALL distinguish those failure modes rather than reporting only a generic immutable-backend failure

#### Scenario: Human-readable output distinguishes degraded replay from invalid replay
- **WHEN** replay verification encounters incomplete replay state, pending-only replay state, or a replay boundary between incompatible proof regimes
- **THEN** the CLI SHALL distinguish degraded verification from invalid replay rather than collapsing both into one hard-failure label

### Requirement: CLI preserves replay rollout guidance
The chain verification CLI SHALL preserve machine-readable replay-boundary classifications in JSON output and SHALL render human-readable rollout guidance that distinguishes supported reservation-backed replay, degraded mixed-regime migration state, and invalid regression back to legacy linkage.

#### Scenario: JSON output preserves rollout boundary classification
- **WHEN** replay verification returns a machine-readable boundary classification for a mixed-regime chain
- **THEN** the CLI JSON output SHALL preserve that classification without replacing it with free-form summary text only

#### Scenario: Human-readable output explains supported reservation-backed replay
- **WHEN** replay verification reports a chain or entry as supported reservation-backed replay
- **THEN** the default terminal output SHALL identify that state as supported reservation-backed replay rather than conflating it with degraded or invalid rollout results

#### Scenario: Human-readable output explains degraded migration state
- **WHEN** replay verification reports a legacy-to-reservation boundary during staged rollout
- **THEN** the default terminal output SHALL identify the result as degraded migration state and SHALL explain that replay visibility exists but continuous reservation-backed predecessor proof is not available across the full history

#### Scenario: Human-readable output explains invalid regression
- **WHEN** replay verification reports a regression from reservation-backed replay into incompatible legacy linkage
- **THEN** the default terminal output SHALL identify that result as invalid regression rather than presenting it as a normal migration boundary or generic replay failure

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

### Requirement: Human-readable verification summary
The CLI SHALL produce a human-readable summary by default that clearly separates replay outcomes from attested-head outcomes and from any explicitly requested troubleshooting outcomes.

#### Scenario: Default terminal output
- **WHEN** the CLI is invoked without `--json`
- **THEN** it SHALL print a concise summary that includes overall status, effective verification mode, replay outcome, attested-head outcome when applicable, and troubleshooting status when applicable

#### Scenario: Pending or incomplete state displayed
- **WHEN** the verified chain contains records that are not yet confirmed in the immutable backend or evidence is unavailable for a pending-only chain
- **THEN** the human-readable output SHALL identify the verification as incomplete or ineligible for evidence-backed verification rather than omitting that state

### Requirement: Supported verification policy flags
The CLI SHALL support the flags `--signer-identity`, `--expected-entry-count`, `--fail-on-pending`, and `--require-tee`.

#### Scenario: Signer identity filter applied
- **WHEN** an operator passes `--signer-identity <value>`
- **THEN** immutable-backend replay verification SHALL apply that identity constraint and report whether matching verified entries remain

#### Scenario: Expected entry count mismatch
- **WHEN** an operator passes `--expected-entry-count <n>` and the normalized result contains a different number of verified entries
- **THEN** the CLI SHALL fail verification and SHALL report the mismatch in the summary and errors output

#### Scenario: Fail on pending enabled
- **WHEN** an operator passes `--fail-on-pending` and one or more records remain pending
- **THEN** the CLI SHALL return a failure result even if structural verification succeeded for the confirmed portion of the chain

#### Scenario: Require TEE enabled without TEE evidence
- **WHEN** an operator passes `--require-tee` and the chain can only be verified in non-TEE fallback mode
- **THEN** the CLI SHALL fail verification and SHALL report that TEE evidence was required but unavailable

### Requirement: Non-TEE results are test-only
The CLI SHALL classify non-TEE fallback verification as test-only behavior rather than production-equivalent TEE verification.

#### Scenario: Non-TEE fallback result
- **WHEN** TruCon reports that RTMR evidence is unavailable and verification proceeds via non-TEE fallback checks
- **THEN** the normalized result SHALL identify the effective verification mode as non-TEE fallback and SHALL mark it as test-only

#### Scenario: TEE result
- **WHEN** RTMR-backed verification is available
- **THEN** the normalized result SHALL identify the effective verification mode as TEE-backed verification

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

### Requirement: CLI reports attestation-storage provenance explicitly
The chain verification CLI SHALL expose Rekor attestation-storage materialization as a distinct provenance source in both JSON diagnostics and human-readable summaries.

#### Scenario: JSON output preserves attestation-storage provenance
- **WHEN** the CLI produces JSON output for a replay that used Rekor attestation storage to materialize verifier-critical payload facts
- **THEN** the normalized result SHALL preserve a machine-readable provenance value of `attestation-storage` for the relevant historical proof dimension

#### Scenario: Human-readable output explains Rekor-hosted materialization
- **WHEN** the CLI produces default terminal output for a verification run that used Rekor attestation storage
- **THEN** the output SHALL explain that historical continuity depended on Rekor-hosted attestation material rather than OCI mirror fallback

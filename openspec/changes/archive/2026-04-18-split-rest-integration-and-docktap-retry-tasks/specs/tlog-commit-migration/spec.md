## MODIFIED Requirements

### Requirement: Business endpoints use TrustedLogAPI for event logging
Each business endpoint (build, publish, launch) SHALL use the `TrustedLogAPI` instance from `app.state.trusted_log` instead of constructing a `ChainedTransparencyLog` instance. The endpoint SHALL call `init_record()` at the start of its async workflow, `add_entry(record_id, entry)` at each step, and `commit_record()` once at the end. Routing trust-event commits through TruCon SHALL NOT change the endpoint's externally observable result contract for the underlying business operation: the endpoint SHALL continue returning its expected identifier and lifecycle/status fields for build, publish, and launch workflows, and SHALL surface transparency degradation separately from core workflow success when TruCon commit submission fails after the business operation succeeds.

#### Scenario: Build endpoint uses TrustedLogAPI
- **WHEN** the build endpoint starts a background build task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, pass the resulting `record_id` through the workflow, and call `commit_record()` after all build steps complete

#### Scenario: Publish endpoint uses TrustedLogAPI
- **WHEN** the publish endpoint starts a background publish task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, accumulate entries via `add_entry()`, and call `commit_record()` after publishing completes

#### Scenario: Launch endpoint uses TrustedLogAPI
- **WHEN** the launch endpoint starts a background launch task
- **THEN** it SHALL call `init_record()` on `app.state.trusted_log`, accumulate entries via `add_entry()`, and call `commit_record()` after launch completes

#### Scenario: Build flow preserves response contract when TruCon commit succeeds
- **WHEN** the build workflow completes successfully and the trust-event commit path to TruCon succeeds
- **THEN** the API SHALL still return the expected build identifier and lifecycle/status fields for the build flow, with transparency data attached without changing the success classification of the build operation

#### Scenario: Publish flow preserves response contract when TruCon commit succeeds
- **WHEN** the publish workflow completes successfully and the trust-event commit path to TruCon succeeds
- **THEN** the API SHALL still return the expected publish/build identifiers and lifecycle/status fields for the publish flow, with transparency data attached without changing the success classification of the publish operation

#### Scenario: Launch flow preserves response contract when TruCon commit succeeds
- **WHEN** the launch workflow completes successfully and the trust-event commit path to TruCon succeeds
- **THEN** the API SHALL still return the expected launch identifier and lifecycle/status fields for the launch flow, with transparency data attached without changing the success classification of the launch operation

#### Scenario: Business flow remains externally successful when trust-event commit degrades
- **WHEN** a build, publish, or launch business workflow completes successfully but the final trust-event commit to TruCon fails or degrades
- **THEN** the API SHALL preserve the workflow's normal result/status shape for the business operation and SHALL report transparency failure or degraded verification state separately instead of converting the whole workflow into an unrelated transport failure
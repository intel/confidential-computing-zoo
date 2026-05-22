## Purpose

Define the requirements for exported attested-head evidence, including its validation contract, quote-backed binding, and read-only export behavior.

## Requirements

### Requirement: Versioned attested head evidence envelope
The system SHALL define a versioned attested head evidence package for remote verification.

#### Scenario: Required envelope fields are present
- **WHEN** a v1 attested head evidence package is produced or validated
- **THEN** it SHALL include `version`, `tee_type`, `chain_id`, `sequence_num`, `head_log_id`, `mr_value`, `generated_at`, `quote`, and `report_data_binding`

#### Scenario: Optional extension fields remain non-breaking
- **WHEN** a v1 attested head evidence package includes `head_event_digest`, `quote_format`, `expires_at`, or `extensions`
- **THEN** validators SHALL treat them as optional fields that do not change the meaning of the required contract

### Requirement: Quote-backed binding covers chain head identity and measured state
The system SHALL require quote-backed binding for `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`.

#### Scenario: Binding metadata identifies the covered fields
- **WHEN** a validator inspects `report_data_binding`
- **THEN** it SHALL find an ordered `bound_fields` list containing `chain_id`, `sequence_num`, `head_log_id`, and `mr_value`

#### Scenario: Binding metadata provides an expected report-data value
- **WHEN** a validator inspects `report_data_binding`
- **THEN** it SHALL find an `algorithm` and `expected_value` sufficient to compare the package binding against quote-backed report data

### Requirement: Event Log 0 remains the epoch baseline anchor
The system SHALL treat Event Log 0 in Rekor as the epoch baseline anchor rather than duplicating baseline evidence into the attested head package.

#### Scenario: Verifier needs baseline evidence
- **WHEN** an operator verifies a chain using exported attested head evidence
- **THEN** baseline origin SHALL be derived from Event Log 0 replay rather than from duplicated `baseline_rtmr` or `ccel_digest` fields inside the attested head package

#### Scenario: Current-head package omits baseline fields
- **WHEN** a v1 attested head evidence package is validated
- **THEN** absence of Event Log 0 baseline fields SHALL NOT invalidate the package because those fields belong to Rekor-backed epoch replay

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

### Requirement: Canonical JSON contract is shared across producers, consumers, and fixtures
The system SHALL define one canonical JSON contract for attested head evidence that is reused by producers, consumers, and test fixtures.

#### Scenario: Fixture validation
- **WHEN** tests load a valid attested head evidence fixture
- **THEN** the same required field and binding rules used by runtime code SHALL accept that fixture without transport-specific assumptions

#### Scenario: Invalid contract rejection
- **WHEN** a package omits a required field or provides incomplete `report_data_binding`
- **THEN** shared validators SHALL reject it as an invalid attested head evidence package

### Requirement: TruCon exports attested head evidence through a read-only HTTP surface
TruCon SHALL expose a read-only HTTP endpoint that returns a v1 attested-head evidence package for a requested chain.

#### Scenario: Export latest confirmed head evidence
- **WHEN** a caller requests evidence for a chain with a confirmed public head
- **THEN** TruCon SHALL return a v1 attested-head evidence package associated with that chain's latest confirmed `head_log_id`

#### Scenario: Read-only export
- **WHEN** a caller invokes the evidence export endpoint
- **THEN** TruCon SHALL treat the request as read-only and SHALL NOT mutate chain ordering state, queue state, or immutable-log state as part of serving the response

### Requirement: Evidence export is strict and confirmed-head only
TruCon SHALL export evidence only for the latest confirmed public head of a chain.

#### Scenario: Chain has no confirmed public head
- **WHEN** a caller requests evidence for a chain whose `head_log_id` is absent because no immutable-log entry is confirmed yet
- **THEN** TruCon SHALL fail the export request rather than returning evidence for a pending local head

#### Scenario: Caller cannot choose an arbitrary historical head in v1
- **WHEN** a caller requests evidence export in v1
- **THEN** TruCon SHALL export only the latest confirmed public head for that chain and SHALL NOT support caller-selected historical head targets

### Requirement: TruCon acquires quote material directly for evidence export
TruCon SHALL acquire quote material directly during export and use it to populate the evidence package.

#### Scenario: Quote acquisition succeeds
- **WHEN** TruCon exports evidence for a chain with a confirmed public head
- **THEN** it SHALL obtain quote material from its configured local TDX quote path and include the resulting quote in the returned evidence package

#### Scenario: Quote acquisition fails
- **WHEN** TruCon cannot obtain quote material during evidence export
- **THEN** the export request SHALL fail rather than returning a partial or degraded evidence package

### Requirement: TruCon computes the report-data binding target before quote comparison
TruCon SHALL compute `report_data_binding.expected_value` from canonical serialization of `chain_id`, `sequence_num`, `head_log_id`, and `mr_value` before comparing that value against quote-backed report data.

#### Scenario: Binding target is generated for export
- **WHEN** TruCon assembles an evidence package
- **THEN** it SHALL derive `expected_value` from the ordered bound fields instead of deriving it from the quote itself

#### Scenario: Quote-backed report data does not match expected binding
- **WHEN** the computed `expected_value` does not match the quote-backed report-data value
- **THEN** TruCon SHALL fail the export request rather than returning an evidence package with mismatched binding data
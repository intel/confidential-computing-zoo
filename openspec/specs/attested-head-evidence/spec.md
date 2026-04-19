## ADDED Requirements

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

### Requirement: Canonical JSON contract is shared across producers, consumers, and fixtures
The system SHALL define one canonical JSON contract for attested head evidence that is reused by producers, consumers, and test fixtures.

#### Scenario: Fixture validation
- **WHEN** tests load a valid attested head evidence fixture
- **THEN** the same required field and binding rules used by runtime code SHALL accept that fixture without transport-specific assumptions

#### Scenario: Invalid contract rejection
- **WHEN** a package omits a required field or provides incomplete `report_data_binding`
- **THEN** shared validators SHALL reject it as an invalid attested head evidence package
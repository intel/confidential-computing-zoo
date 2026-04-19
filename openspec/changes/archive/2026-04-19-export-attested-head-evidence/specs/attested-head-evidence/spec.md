## ADDED Requirements

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
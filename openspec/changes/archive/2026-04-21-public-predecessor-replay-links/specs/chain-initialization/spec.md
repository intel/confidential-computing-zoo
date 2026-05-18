## ADDED Requirements

### Requirement: Event Log 0 uses explicit null predecessor fields
Event Log 0 SHALL use the same signed public replay contract as later records, with explicit null predecessor fields.

#### Scenario: Baseline predecessor fields
- **WHEN** tc_api or TruCon constructs Event Log 0 for a chain
- **THEN** the signed public replay payload SHALL include `sequence_num = 1`, `prev_event_digest = null`, and `prev_lookup_hash = null`

#### Scenario: Baseline replay remains schema-consistent
- **WHEN** a verifier replays Event Log 0 together with later records
- **THEN** it SHALL interpret Event Log 0 as the null-predecessor instance of the same replay schema rather than as a schema exception

### Requirement: Successor records reference baseline through the signed replay contract
The first non-baseline record after Event Log 0 SHALL reference the baseline using the same signed predecessor fields used by all later records.

#### Scenario: First business event after initialization
- **WHEN** the first business or runtime record is committed after Event Log 0
- **THEN** its signed replay payload SHALL carry `sequence_num = 2`, `prev_event_digest` equal to the baseline event digest, and `prev_lookup_hash` equal to the baseline DSSE `payloadHash(sha256)`

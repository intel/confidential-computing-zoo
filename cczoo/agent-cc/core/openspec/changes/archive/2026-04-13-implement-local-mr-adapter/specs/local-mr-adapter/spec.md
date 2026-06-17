## ADDED Requirements

### Requirement: Local Measurement Register Interface Definition
The system SHALL define a `LocalMRAdapter` interface capable of extending and reading local machine hardware measurement registers.

#### Scenario: Interface extraction
- **WHEN** the trusted container log is used
- **THEN** it accepts a `LocalMRAdapter` rather than a boolean to securely manage RTMR values.
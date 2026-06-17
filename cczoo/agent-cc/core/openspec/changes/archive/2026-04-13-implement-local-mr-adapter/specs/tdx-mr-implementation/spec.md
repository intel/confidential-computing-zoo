## ADDED Requirements

### Requirement: TdxMRAdapter Implementation
The system SHALL provide a concrete `TdxMRAdapter` class implementing `LocalMRAdapter` that safely interacts with the TDX OS-level subsystem (e.g. sysfs).

#### Scenario: Read TDX Measurement Register
- **WHEN** the user calls to get the measurement register value
- **THEN** the adapter queries the TDX sysfs node, or relevant OS mechanism, to securely fetch the current RTMR value.

#### Scenario: Extend TDX Measurement Register
- **WHEN** an extension is requested via the API
- **THEN** the `TdxMRAdapter` writes the provided hash or data to the proper TDX RTMR interface effectively sealing the new state.
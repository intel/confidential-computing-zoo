## Purpose

Define the requirements for the current trusted-log audit snapshot surface after legacy transparency snapshot files were removed.

## Requirements

### Requirement: Legacy transparency files are no longer produced or consumed
The system SHALL no longer produce or consume legacy transparency snapshot files such as `.sigstore.json`. Trusted-log audit data SHALL flow through current TruCon commit receipts and verification surfaces instead.

#### Scenario: Legacy file production is absent
- **WHEN** a current build, publish, or launch workflow completes
- **THEN** the system SHALL NOT emit legacy transparency snapshot files as an audit artifact

#### Scenario: Legacy file consumption is absent
- **WHEN** verification or audit tooling operates on current trusted-log data
- **THEN** the supported audit path SHALL use current TruCon receipts and verification APIs rather than legacy snapshot file readers

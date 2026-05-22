## ADDED Requirements

### Requirement: Canonical service name
The TruCon core service SHALL be identified by the name "TruCon" in all code, configuration, documentation, and deployment artifacts. The prior name "Trust API" SHALL NOT be used.

#### Scenario: Python module filename
- **WHEN** the TruCon service module is created or referenced
- **THEN** the filename SHALL be `trucon.py` and the uvicorn target SHALL be `trucon:app`

#### Scenario: Environment variable
- **WHEN** the tc_api or deployment configuration references the TruCon service URL
- **THEN** the environment variable SHALL be named `TRUCON_URL`

#### Scenario: Docker Compose service name
- **WHEN** the TruCon service is defined in docker-compose.yml
- **THEN** the service name SHALL be `trucon`

#### Scenario: Python parameter naming
- **WHEN** a Python function or constructor accepts the TruCon service URL
- **THEN** the parameter SHALL be named `trucon_url`

### Requirement: Config default URL
The `TRUCON_URL` configuration variable SHALL default to `http://127.0.0.1:8001` when not explicitly set.

#### Scenario: Default URL used when not configured
- **WHEN** no `TRUCON_URL` environment variable is set
- **THEN** the system SHALL use `http://127.0.0.1:8001` as the TruCon service URL

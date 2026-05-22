## MODIFIED Requirements

### Requirement: Repository has a monorepo directory structure
The repository root SHALL contain separate top-level directories for each logical unit: `tc-api/` for the API service package, `tlog/` for the standalone trusted-log project (including backend implementations), and `trust-service/` for the attestation trust service. Trusted-log backend implementations SHALL NOT exist as separate top-level Python projects once consolidated.

#### Scenario: tc-api files are in tc-api/ subdirectory
- **WHEN** inspecting the repository root
- **THEN** `tc-api/` SHALL contain `pyproject.toml`, `tc_api/`, `tests/`, `docs/`, `examples/`, `openspec/`, `setup.sh`, `start.sh`, `run_tests.sh`, `AGENTS.md`, `README.md`, `.env.example`, `.github/`, and `.vscode/`
- **AND** none of these files SHALL exist at the repository root

#### Scenario: tlog is the only trusted-log Python project at the repository root
- **WHEN** inspecting the repository root
- **THEN** `tlog/` SHALL exist as the standalone trusted-log project
- **AND** `tlog-rekor/` SHALL NOT exist as a separate top-level Python project
- **AND** `tlog-onchain/` SHALL NOT exist as a separate top-level Python project

#### Scenario: trust-service is named trust-service
- **WHEN** inspecting the repository root
- **THEN** `trust-service/` SHALL exist containing the attestation service Dockerfile and configuration files
- **AND** `aa_asr_cdh/` SHALL NOT exist

### Requirement: Dockerfile uses targeted COPY commands
The Dockerfile SHALL explicitly COPY only the packages needed for the container image, rather than copying the entire repository.

#### Scenario: Dockerfile copies consolidated trusted-log project
- **WHEN** inspecting the Dockerfile
- **THEN** it SHALL contain separate COPY commands for `tlog/` and `tc-api/`
- **AND** it SHALL NOT copy `tlog-rekor/` or `tlog-onchain/` as separate top-level projects

#### Scenario: Dockerfile WORKDIR is tc-api
- **WHEN** the container starts
- **THEN** WORKDIR SHALL be `/app/tc-api`
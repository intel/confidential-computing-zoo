## ADDED Requirements

### Requirement: Repository has a monorepo directory structure
The repository root SHALL contain separate top-level directories for each logical unit: `tc-api/` for the API service package, `tlog/` for the standalone trusted-log types, `tlog-rekor/` for the Rekor backend adapter, `tlog-onchain/` for the on-chain backend adapter, and `trust-service/` for the attestation trust service.

#### Scenario: tc-api files are in tc-api/ subdirectory
- **WHEN** inspecting the repository root
- **THEN** `tc-api/` SHALL contain `pyproject.toml`, `src/`, `tests/`, `docs/`, `examples/`, `openspec/`, `setup.sh`, `start.sh`, `run_tests.sh`, `AGENTS.md`, `README.md`, `.env.example`, `.github/`, and `.vscode/`
- **AND** none of these files SHALL exist at the repository root

#### Scenario: tlog packages remain at repository root
- **WHEN** inspecting the repository root
- **THEN** `tlog/`, `tlog-rekor/`, and `tlog-onchain/` SHALL exist at the repository root with their contents unchanged

#### Scenario: trust-service is named trust-service
- **WHEN** inspecting the repository root
- **THEN** `trust-service/` SHALL exist containing the attestation service Dockerfile and configuration files
- **AND** `aa_asr_cdh/` SHALL NOT exist

### Requirement: System-level files remain at repository root
The `Dockerfile`, `docker-compose.yml`, and `deploy/` directory SHALL remain at the repository root because they operate across multiple packages.

#### Scenario: Dockerfile is at repo root
- **WHEN** building the Docker image
- **THEN** `Dockerfile` SHALL be at the repository root with build context set to the repository root

#### Scenario: docker-compose.yml is at repo root
- **WHEN** running `docker-compose up`
- **THEN** `docker-compose.yml` SHALL be at the repository root

### Requirement: Scripts are split between root and tc-api
System-level orchestration scripts SHALL remain at `scripts/` in the repository root. tc-api-specific scripts SHALL be located at `tc-api/scripts/`.

#### Scenario: System-level scripts stay at root
- **WHEN** inspecting `scripts/` at the repository root
- **THEN** it SHALL contain `dev-up.sh`, `trust_service.sh`, `create_encrypted_vfs.sh`, `mount_encrypted_vfs.sh`, and `unmount_encrypted_vfs.sh`

#### Scenario: tc-api scripts are in tc-api/scripts/
- **WHEN** inspecting `tc-api/scripts/`
- **THEN** it SHALL contain tc-api-specific operator helpers including `run_docktap_oob_atomic.py`, `verify_current_attested_head.py`, and `tdvm_smoke_test.py`

### Requirement: Dockerfile uses targeted COPY commands
The Dockerfile SHALL explicitly COPY only the packages needed for the container image, rather than copying the entire repository.

#### Scenario: Dockerfile copies individual packages
- **WHEN** inspecting the Dockerfile
- **THEN** it SHALL contain separate COPY commands for `tlog/`, `tlog-rekor/`, and `tc-api/`
- **AND** it SHALL NOT use `COPY . /app/` to copy the entire repository

#### Scenario: Dockerfile WORKDIR is tc-api
- **WHEN** the container starts
- **THEN** WORKDIR SHALL be `/app/tc-api`

### Requirement: docker-compose volume mounts reference tc-api subdirectory
Volume mounts for tc-api runtime directories SHALL reference the `tc-api/` subdirectory on the host side.

#### Scenario: uploads volume mount uses tc-api path
- **WHEN** inspecting the tc-api service in docker-compose.yml
- **THEN** the uploads volume mount source SHALL be `./tc-api/uploads`

#### Scenario: builds volume mount uses tc-api path
- **WHEN** inspecting the tc-api service in docker-compose.yml
- **THEN** the builds volume mount source SHALL be `./tc-api/builds`

### Requirement: Root README describes monorepo structure
A `README.md` at the repository root SHALL describe the overall monorepo structure, listing each top-level directory and its purpose.

#### Scenario: Root README exists and describes layout
- **WHEN** inspecting `README.md` at the repository root
- **THEN** it SHALL list and describe `tc-api/`, `tlog/`, `tlog-rekor/`, `tlog-onchain/`, `trust-service/`, and system-level files
- **AND** `tc-api/README.md` SHALL contain the original tc-api-specific documentation

### Requirement: No dead remnants exist
After the restructure, no dead code, tombstone packages, or orphaned directories SHALL remain.

#### Scenario: No docktap pycache remnants
- **WHEN** inspecting the repository root
- **THEN** there SHALL be no `docktap/` directory at the root

#### Scenario: No tlog tombstone package
- **WHEN** inspecting `tc-api/src/tc_api/`
- **THEN** there SHALL be no `tlog/` subdirectory (the tombstone package SHALL be removed)

#### Scenario: No stray test files at root
- **WHEN** inspecting the repository root
- **THEN** `tdvm_smoke_test.py` SHALL NOT exist at the root (it SHALL be in `tc-api/scripts/`)

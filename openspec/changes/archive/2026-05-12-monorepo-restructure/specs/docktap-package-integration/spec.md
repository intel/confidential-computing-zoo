## MODIFIED Requirements

### Requirement: Deployment files reference tc_api.docktap
Deployment entry points in `docker-compose.yml` and `start.sh` SHALL reference the `tc_api.docktap.main` module path. After monorepo restructure, `start.sh` is located at `tc-api/start.sh` and volume mounts in `docker-compose.yml` reference the `tc-api/` subdirectory.

#### Scenario: docker-compose uses new module path
- **WHEN** inspecting the docktap service in `docker-compose.yml`
- **THEN** the command SHALL reference `tc_api.docktap.main` (not `docktap.main`)

#### Scenario: start.sh uses new module path
- **WHEN** inspecting docktap invocation in `tc-api/start.sh`
- **THEN** the command SHALL use `python -m tc_api.docktap.main` or the `tc-docktap` entry point

#### Scenario: docker-compose docktap logs volume uses tc-api path
- **WHEN** inspecting the docktap service volumes in `docker-compose.yml`
- **THEN** the logs volume mount source SHALL be `./tc-api/logs`

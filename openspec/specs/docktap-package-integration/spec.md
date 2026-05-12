## Purpose

Define the requirements for docktap's integration as a sub-package of tc_api, including import conventions, CLI entry points, and deployment configuration.

## Requirements

### Requirement: Docktap is a sub-package of tc_api
The `docktap` module SHALL be located at `src/tc_api/docktap/` and be installable as part of the `tc-api` package. It SHALL NOT exist as a top-level directory or use `sys.path` manipulation to resolve imports.

#### Scenario: docktap is discoverable as tc_api.docktap
- **WHEN** `tc-api` is installed via `pip install -e .`
- **THEN** `import tc_api.docktap` SHALL succeed and `python -m tc_api.docktap.main` SHALL start the docktap proxy

#### Scenario: docktap uses relative imports internally
- **WHEN** inspecting import statements in `src/tc_api/docktap/*.py` and `src/tc_api/docktap/proxy/*.py`
- **THEN** intra-package references SHALL use relative imports (e.g., `from .trucon_client import ...`, `from .proxy.docker_proxy import ...`)
- **AND** no file SHALL contain `sys.path.insert` or `sys.path.append` calls

#### Scenario: docktap tests use package imports
- **WHEN** inspecting import statements in `src/tc_api/docktap/tests/*.py`
- **THEN** imports of docktap modules SHALL use either relative imports or absolute `tc_api.docktap.*` imports
- **AND** `conftest.py` SHALL NOT manipulate `sys.path`

### Requirement: tc-docktap CLI entry point
The `tc-docktap` command SHALL be registered as a setuptools console script entry point, consistent with `tc-api`, `tc-trucon`, and `tc-verify`.

#### Scenario: tc-docktap is available after install
- **WHEN** `tc-api` is installed via `pip install -e .`
- **THEN** `tc-docktap --help` SHALL be available on the PATH
- **AND** it SHALL invoke `tc_api.docktap.main:main`

### Requirement: Deployment files reference tc_api.docktap
Deployment entry points in `docker-compose.yml` and `start.sh` SHALL reference the `tc_api.docktap.main` module path.

#### Scenario: docker-compose uses new module path
- **WHEN** inspecting the docktap service in `docker-compose.yml`
- **THEN** the command SHALL reference `tc_api.docktap.main` (not `docktap.main`)

#### Scenario: start.sh uses new module path
- **WHEN** inspecting docktap invocation in `start.sh`
- **THEN** the command SHALL use `python -m tc_api.docktap.main` or the `tc-docktap` entry point

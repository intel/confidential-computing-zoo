## MODIFIED Requirements

### Requirement: Three-layer package structure
The codebase SHALL organize trusted-log related code into three distinct layers: a standalone `tlog` package (independent project), a TruCon service package (`trucon/` within `tc-api`), and a tc_api-side client module (`tlog_client.py` within `tc-api`). The `tlog` package is a separate installable project, not a sub-package of `tc_api`.

#### Scenario: tlog/ is a standalone project with its own pyproject.toml
- **WHEN** inspecting the `tlog/` directory at the monorepo root
- **THEN** it SHALL have its own `pyproject.toml` and be installable independently via `pip install -e tlog/`

#### Scenario: tlog/ contains only shared contracts and digest computation
- **WHEN** inspecting the `tlog/src/tlog/` package
- **THEN** it SHALL contain domain types (`types.py`), error definitions (`errors.py`), abstract adapter interfaces (`immutable.py`, `local_mr.py`), and consolidated digest functions (`digest.py`) with no concrete implementations, database code, or third-party dependencies

#### Scenario: trucon/ contains sequencer internals
- **WHEN** inspecting the `tc-api/src/tc_api/trucon/` package
- **THEN** it SHALL contain the FastAPI sequencer app (`app.py`), SQLite queue operations (`database.py`), and platform-specific adapters under `adapters/` (`tdx_mr.py`, `tdx_quote.py`, `ccel.py`)
- **AND** `adapters/` SHALL NOT contain `sigstore.py` or `oci_mirror.py` — those files SHALL NOT exist in the directory

#### Scenario: tlog_client.py is the tc_api-side interface
- **WHEN** inspecting `tc-api/src/tc_api/tlog_client.py`
- **THEN** it SHALL contain the `TrustedLogAPI` class that performs DSSE signing and communicates with TruCon, importing domain types from the standalone `tlog` package

#### Scenario: src/tc_api/tlog/ tombstone is removed
- **WHEN** inspecting `tc-api/src/tc_api/`
- **THEN** there SHALL be no `tlog/` subdirectory

#### Scenario: setup.sh installs sibling tlog packages
- **WHEN** running `tc-api/setup.sh`
- **THEN** it SHALL install `tlog` and `tlog-rekor` from sibling directories (`../tlog`, `../tlog-rekor`) in editable mode alongside the tc-api package itself

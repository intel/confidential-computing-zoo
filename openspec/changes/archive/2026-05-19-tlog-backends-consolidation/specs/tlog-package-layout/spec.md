## MODIFIED Requirements

### Requirement: Three-layer package structure
The codebase SHALL organize trusted-log related code into three distinct layers: a standalone `tlog` package (independent project), a TruCon service package (`trucon/` within `tc-api`), and a tc_api-side client module (`tlog_client.py` within `tc-api`). The standalone `tlog` project SHALL contain both core trusted-log contracts and backend implementation namespaces, but SHALL NOT absorb TruCon runtime orchestration.

#### Scenario: tlog/ is a standalone project with its own pyproject.toml
- **WHEN** inspecting the `tlog/` directory at the monorepo root
- **THEN** it SHALL have its own `pyproject.toml` and be installable independently via `pip install -e tlog/`

#### Scenario: tlog/ contains core contracts and backend namespaces
- **WHEN** inspecting the `tlog/tlog/` package
- **THEN** it SHALL contain domain types (`types.py`), error definitions (`errors.py`), abstract adapter interfaces (`immutable.py`, `local_mr.py`), consolidated digest functions (`digest.py`), and backend namespaces under `backends/`

#### Scenario: trucon/ contains sequencer internals
- **WHEN** inspecting the `tc-api/tc_api/trucon/` package
- **THEN** it SHALL contain the FastAPI sequencer app (`app.py`), SQLite queue operations (`database.py`), and platform-specific adapters under `adapters/` (`tdx_mr.py`, `tdx_quote.py`, `ccel.py`)
- **AND** `adapters/` SHALL NOT contain immutable-log backend implementations

#### Scenario: tlog_client.py is the tc_api-side interface
- **WHEN** inspecting `tc-api/tc_api/tlog_client.py`
- **THEN** it SHALL contain the `TrustedLogAPI` class that performs DSSE signing and communicates with TruCon, importing domain types from the standalone `tlog` package

#### Scenario: tc_api/tlog/ tombstone is removed
- **WHEN** inspecting `tc-api/tc_api/`
- **THEN** there SHALL be no `tlog/` subdirectory

#### Scenario: setup.sh installs only the consolidated tlog project
- **WHEN** running `tc-api/setup.sh`
- **THEN** it SHALL install the standalone `tlog` project from the sibling `../tlog` directory in editable mode alongside the tc-api package itself

### Requirement: Import path conventions
Each layer SHALL use import paths consistent with its package location. The tc_api business layer (`api/_legacy.py`, `services/*`) SHALL import shared types from `tlog` (standalone package) and the client from `tc_api.transparency.commit_client`. TruCon internals SHALL import shared types from `tlog` and platform adapter implementations from `tc_api.trucon.adapters`. Immutable-log backend adapters SHALL be imported from backend namespaces inside `tlog`.

#### Scenario: api/_legacy.py imports from standalone tlog
- **WHEN** `api/_legacy.py` imports trusted-log types and client
- **THEN** it SHALL use `from tlog.types import Entry` and `from tc_api.transparency.commit_client import TrustedLogAPI`

#### Scenario: trucon/app.py imports from correct layers
- **WHEN** `trucon/app.py` imports database and adapters
- **THEN** it SHALL use `from .database import ...` for queue operations and `from tlog.immutable import ImmutableLogAdapter` for the adapter ABC

#### Scenario: backend imports use consolidated tlog namespace
- **WHEN** first-party code imports immutable-log backend implementations
- **THEN** it SHALL use paths under `tlog.backends.*` rather than `tlog_rekor.*` or `tlog_onchain.*`
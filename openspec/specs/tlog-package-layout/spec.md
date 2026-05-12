## Purpose

Define the requirements for the trusted-log package layout and the boundaries between shared types, TruCon internals, and tc_api client code.

## Requirements

### Requirement: Three-layer package structure
The codebase SHALL organize trusted-log related code into three distinct layers: a standalone `tlog` package (independent project), a TruCon service package (`trucon/` within `tc-api`), and a tc_api-side client module (`tlog_client.py` within `tc-api`). The `tlog` package is a separate installable project, not a sub-package of `tc_api`.

#### Scenario: tlog/ is a standalone project with its own pyproject.toml
- **WHEN** inspecting the `tlog/` directory at the monorepo root (or `agent-cc/core/tlog/`)
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

#### Scenario: src/tc_api/tlog/ contains no shim files
- **WHEN** inspecting `src/tc_api/tlog/`
- **THEN** it SHALL contain only `__init__.py` with a tombstone notice directing users to the standalone `tlog` package
- **AND** it SHALL NOT contain `types.py`, `errors.py`, `immutable.py`, or `local_mr.py`

### Requirement: Import path conventions
Each layer SHALL use import paths consistent with its package location. The tc_api business layer (`main.py`, `services.py`) SHALL import shared types from `tlog` (standalone package) and the client from `tc_api.tlog_client`. TruCon internals SHALL import shared types from `tlog` and platform adapter implementations from `tc_api.trucon.adapters`. Immutable-log backend adapters SHALL be imported from their own packages (`tlog_rekor`, `tlog_onchain`).

#### Scenario: main.py imports from standalone tlog
- **WHEN** `main.py` imports trusted-log types and client
- **THEN** it SHALL use `from tlog.types import Entry` and `from tc_api.tlog_client import TrustedLogAPI`

#### Scenario: trucon/app.py imports from correct layers
- **WHEN** `trucon/app.py` imports database and adapters
- **THEN** it SHALL use `from .database import ...` for queue operations and `from tlog.immutable import ImmutableLogAdapter` for the adapter ABC

### Requirement: No upward imports from trucon to tc_api
The `trucon/` package SHALL NOT import from `tc_api.config`, `tc_api.main`, `tc_api.services`, or `tc_api.models`. Configuration values (such as database path) SHALL be injected via module-level defaults or environment variables.

#### Scenario: trucon/database.py does not import tc_api.config
- **WHEN** `trucon/database.py` needs the database file path
- **THEN** it SHALL use a module-level default (`/dev/shm/tc_api_queue/queue.db`) that can be overridden, rather than importing from `tc_api.config`

### Requirement: Entry point update for TruCon
The TruCon uvicorn entry point SHALL reference the module path `tc_api.trucon.app:app`.

#### Scenario: TruCon starts via entry point
- **WHEN** TruCon is started via uvicorn or `python -m tc_api.trucon.app`
- **THEN** the FastAPI application SHALL load successfully from `tc_api.trucon.app:app`

### Requirement: Legacy package removed
The `trusted_container_log/` directory SHALL be completely removed after restructure. No files SHALL remain in the old location.

#### Scenario: No trusted_container_log directory exists
- **WHEN** the restructure is complete
- **THEN** `src/tc_api/trusted_container_log/` SHALL NOT exist as a directory

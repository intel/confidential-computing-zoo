## ADDED Requirements

### Requirement: Three-layer package structure
The codebase SHALL organize trusted-log related code into three distinct layers: a shared domain package (`tlog/`), a TruCon service package (`trucon/`), and a tc_api-side client module (`tlog_client.py`).

#### Scenario: tlog/ contains only shared contracts
- **WHEN** inspecting the `src/tc_api/tlog/` package
- **THEN** it SHALL contain only domain types (`types.py`), error definitions (`errors.py`), and abstract adapter interfaces (`immutable.py`, `local_mr.py`) with no concrete implementations or database code

#### Scenario: trucon/ contains sequencer internals
- **WHEN** inspecting the `src/tc_api/trucon/` package
- **THEN** it SHALL contain the FastAPI sequencer app (`app.py`), SQLite queue operations (`database.py`), and concrete adapter implementations under `adapters/` (`sigstore.py`, `tdx_mr.py`)

#### Scenario: tlog_client.py is the tc_api-side interface
- **WHEN** inspecting `src/tc_api/tlog_client.py`
- **THEN** it SHALL contain the `TrustedLogAPI` class that performs DSSE signing and REST calls to TruCon, previously located at `trusted_container_log/api.py`

### Requirement: Import path conventions
Each layer SHALL use import paths consistent with its package location. The tc_api business layer (`api/_legacy.py`, `services/*`) SHALL import shared types from `tlog` and the client from `tc_api.trust.commit_client`. TruCon internals SHALL import shared types from `tlog` and adapter implementations from `tc_api.trucon.adapters`.

#### Scenario: main.py imports from correct layers
- **WHEN** `main.py` imports trusted-log types and client
- **THEN** it SHALL use `from .tlog.types import Entry` and `from .tlog_client import TrustedLogAPI`

#### Scenario: trucon/app.py imports from correct layers
- **WHEN** `trucon/app.py` imports database and adapters
- **THEN** it SHALL use `from .database import ...` for queue operations and `from .adapters.sigstore import SigstoreLogAdapter` for adapter implementations

### Requirement: No upward imports from trucon to tc_api
The `trucon/` package SHALL NOT import from `tc_api.config`, `tc_api.api`, `tc_api.services`, or `tc_api.models`. Configuration values (such as database path) SHALL be injected via module-level defaults or environment variables.

#### Scenario: trucon/database.py does not import tc_api.config
- **WHEN** `trucon/database.py` needs the database file path
- **THEN** it SHALL use a module-level default (`/dev/shm/tc_api_queue/queue.db`) that can be overridden, rather than importing from `tc_api.config`

### Requirement: Entry point update for TruCon
The TruCon uvicorn entry point SHALL reference the new module path `tc_api.trucon.app:app` instead of the previous `tc_api.trucon:app`.

#### Scenario: TruCon starts via updated entry point
- **WHEN** TruCon is started via uvicorn or `python -m tc_api.trucon.app`
- **THEN** the FastAPI application SHALL load successfully from `tc_api.trucon.app:app`

### Requirement: Legacy package removed
The `trusted_container_log/` directory SHALL be completely removed after restructure. No files SHALL remain in the old location.

#### Scenario: No trusted_container_log directory exists
- **WHEN** the restructure is complete
- **THEN** `src/tc_api/trusted_container_log/` SHALL NOT exist as a directory

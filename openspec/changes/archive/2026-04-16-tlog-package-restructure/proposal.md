## Why

The `trusted_container_log/` package currently houses code belonging to three distinct architectural roles: shared domain types (used by everyone), TruCon sequencer internals (database, MR adapter implementations), and the tc_api-side log client (DSSE signing + REST). Phase 1A/1B cleaned up the legacy code, but the flat directory still conflates these roles, making it unclear which code belongs to which deployment boundary. Restructuring now prepares the codebase for future TruCon independent packaging (Phase 3) and makes the adapter-interface / adapter-implementation boundary explicit.

## What Changes

- **BREAKING**: Rename `trusted_container_log/` to `tlog/` — shared domain layer containing only types, errors, and abstract adapter interfaces (ABCs)
- **BREAKING**: Move `trusted_container_log/database.py` to new `trucon/database.py` subpackage
- **BREAKING**: Split `tlog_impl.py` — ABC (`ImmutableLogAdapter`) stays in `tlog/immutable.py`, implementation (`SigstoreLogAdapter`) moves to `trucon/adapters/sigstore.py`
- **BREAKING**: Split `local_mr.py` — ABC (`LocalMRAdapter`) stays in `tlog/local_mr.py`, implementation (`TdxMRAdapter`) moves to `trucon/adapters/tdx_mr.py`
- **BREAKING**: Move `trusted_container_log/api.py` to `tc_api/tlog_client.py` (top-level module, not inside tlog/)
- **BREAKING**: Move `trucon.py` to `trucon/app.py` within the new `trucon/` subpackage
- Update all import paths across `main.py`, `services.py`, and `trucon/app.py`

## Capabilities

### New Capabilities
- `tlog-package-layout`: Defines the three-layer package structure (`tlog/`, `trucon/`, `tlog_client.py`) and the import path conventions for each layer

### Modified Capabilities

_(No spec-level behavior changes — this is a pure structural refactor. All existing functionality remains identical.)_

## Impact

- **`src/tc_api/trusted_container_log/`**: Deleted entirely; replaced by `src/tc_api/tlog/`
- **`src/tc_api/trucon.py`**: Moves to `src/tc_api/trucon/app.py` with submit daemon and database alongside
- **`src/tc_api/tlog_client.py`**: New location for the tc_api-side log client (formerly `api.py`)
- **`src/tc_api/main.py`**: Import path changes (`from .tlog.types import Entry`, `from .tlog_client import TrustedLogAPI`)
- **`src/tc_api/services.py`**: Import path changes
- **`pyproject.toml`**: Entry point for TruCon changes from `tc_api.trucon:app` to `tc_api.trucon.app:app`
- **`start.sh`**: Update uvicorn target if TruCon start command references module path

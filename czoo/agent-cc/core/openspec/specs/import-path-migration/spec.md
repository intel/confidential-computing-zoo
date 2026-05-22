## ADDED Requirements

### Requirement: Compatibility shims at old import paths
After file extraction, thin re-export shims SHALL be placed at the original `tc_api.tlog.*` import paths to prevent immediate breakage of all consumers.

#### Scenario: tc_api.tlog.types re-exports from tlog.types
- **WHEN** code imports `from tc_api.tlog.types import Entry`
- **THEN** the import SHALL succeed by re-exporting from `tlog.types`

#### Scenario: tc_api.tlog.immutable re-exports from tlog.immutable
- **WHEN** code imports `from tc_api.tlog.immutable import ImmutableLogAdapter`
- **THEN** the import SHALL succeed by re-exporting from `tlog.immutable`

#### Scenario: tc_api.tlog.errors re-exports from tlog.errors
- **WHEN** code imports `from tc_api.tlog.errors import TrustedLogError`
- **THEN** the import SHALL succeed by re-exporting from `tlog.errors`

#### Scenario: tc_api.tlog.local_mr re-exports from tlog.local_mr
- **WHEN** code imports `from tc_api.tlog.local_mr import LocalMRAdapter`
- **THEN** the import SHALL succeed by re-exporting from `tlog.local_mr`

### Requirement: All tc_api internal imports SHALL be updated to use tlog directly
All files within `tc_api`, `trucon`, `docktap`, and `cli` SHALL import from the `tlog` package directly rather than through `tc_api.tlog`.

#### Scenario: tc_api source files import from tlog
- **WHEN** inspecting import statements in `main.py`, `services.py`, `tlog_client.py`
- **THEN** imports of domain types SHALL use `from tlog.types import ...` instead of `from tc_api.tlog.types import ...`

#### Scenario: trucon source files import from tlog
- **WHEN** inspecting import statements in `trucon/app.py`, `trucon/adapters/tdx_mr.py`
- **THEN** imports of ABCs SHALL use `from tlog.local_mr import LocalMRAdapter` instead of `from tc_api.tlog.local_mr import LocalMRAdapter`

#### Scenario: docktap source files import from tlog
- **WHEN** inspecting import statements in `docktap/trucon_client.py`
- **THEN** imports of `Entry` SHALL use `from tlog.types import Entry` instead of `from tc_api.tlog.types import Entry`

### Requirement: SigstoreLogAdapter imports SHALL reference tlog_rekor
All files that import `SigstoreLogAdapter` SHALL use the new import path `from tlog_rekor.adapter import SigstoreLogAdapter`.

#### Scenario: trucon submit daemon uses new import path
- **WHEN** inspecting the submit daemon's adapter loading code
- **THEN** `SigstoreLogAdapter` SHALL be imported from `tlog_rekor.adapter`

#### Scenario: cli/verify uses new import path
- **WHEN** inspecting `cli/verify.py`
- **THEN** `SigstoreLogAdapter` SHALL be imported from `tlog_rekor.adapter` instead of `tc_api.trucon.adapters.sigstore`

#### Scenario: Test files use new import path
- **WHEN** inspecting test files that reference `SigstoreLogAdapter`
- **THEN** they SHALL import from `tlog_rekor.adapter` or mock the new path

### Requirement: Digest function imports SHALL reference tlog.digest
All files that use `canonical_json`, `compute_entry_digest`, or `compute_event_digest` SHALL import from `tlog.digest` instead of using local duplicates.

#### Scenario: tlog_client.py imports from tlog.digest
- **WHEN** inspecting `tlog_client.py`
- **THEN** digest functions SHALL be imported from `tlog.digest` and the local definitions SHALL be removed

#### Scenario: sigstore_baseline.py imports from tlog.digest
- **WHEN** inspecting `sigstore_baseline.py`
- **THEN** the private `_canonical_json`, `_compute_entry_digest`, `_compute_event_digest` SHALL be replaced with imports from `tlog.digest`

#### Scenario: owner_attestation.py imports from tlog.digest
- **WHEN** inspecting `trucon/owner_attestation.py`
- **THEN** the local `canonical_json` SHALL be replaced with an import from `tlog.digest`

### Requirement: Shims SHALL be removed after all imports are updated
Once all import paths across the codebase are updated to reference `tlog` and `tlog_rekor` directly, the compatibility shims in `tc_api.tlog` SHALL be removed.

#### Scenario: No shim files remain after migration
- **WHEN** the import path migration is complete
- **THEN** `tc_api/tlog/types.py`, `tc_api/tlog/immutable.py`, `tc_api/tlog/errors.py`, and `tc_api/tlog/local_mr.py` SHALL either be deleted or contain only tc_api-specific additions (not re-exports)

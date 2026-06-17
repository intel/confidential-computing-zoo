## ADDED Requirements

### Requirement: tlog is an independent installable Python package
The `tlog` package SHALL be installable via `pip install -e tlog/` (or equivalent) without any dependency on `tc_api` or any other project in the monorepo. Backend-specific third-party dependencies SHALL remain optional rather than required by the base install.

#### Scenario: Clean install of base tlog
- **WHEN** `pip install -e tlog/` is run in a fresh virtual environment
- **THEN** the installation SHALL succeed without requiring Rekor-specific third-party dependencies

#### Scenario: tlog has its own pyproject.toml
- **WHEN** inspecting the `tlog/` project directory
- **THEN** a `pyproject.toml` SHALL exist declaring the package name, version, package discovery, and optional dependency groups for backend integrations

### Requirement: tlog contains shared domain types
The `tlog` package SHALL contain all shared domain types that are consumed across multiple projects.

#### Scenario: types.py contains all domain dataclasses
- **WHEN** inspecting `tlog/tlog/types.py`
- **THEN** it SHALL contain `Entry`, `Record`, `EventLog`, `RecordContext`, `CommitResult`, `CommitQueueStatus`, `LatestState`, `VerificationResult`, and `SubmitStatus`

#### Scenario: errors.py contains all domain errors
- **WHEN** inspecting `tlog/tlog/errors.py`
- **THEN** it SHALL contain `TrustedLogError`, `RecordNotFoundError`, `BackendSubmitError`, and `VerificationError`

### Requirement: tlog contains abstract adapter interfaces
The `tlog` package SHALL contain the abstract base classes for immutable log and local measurement register adapters.

#### Scenario: immutable.py defines ImmutableLogAdapter ABC
- **WHEN** inspecting `tlog/tlog/immutable.py`
- **THEN** it SHALL define `ImmutableLogAdapter` as an abstract base class with methods `submit_bundle`, `get_entry`, `traverse`, and `find_entries_by_payload_hash`

#### Scenario: local_mr.py defines LocalMRAdapter ABC
- **WHEN** inspecting `tlog/tlog/local_mr.py`
- **THEN** it SHALL define `LocalMRAdapter` as an abstract base class with methods `read` and `extend`

### Requirement: ImmutableLogAdapter SHALL NOT depend on sigstore
The `ImmutableLogAdapter` ABC SHALL NOT import from `sigstore` or any backend-specific library. The `submit_bundle` method SHALL accept a `str` parameter (serialized bundle JSON) instead of `sigstore.models.Bundle`.

#### Scenario: submit_bundle accepts str
- **WHEN** inspecting the `submit_bundle` method signature in `ImmutableLogAdapter`
- **THEN** the `bundle` parameter type SHALL be `str`, not `sigstore.models.Bundle`

#### Scenario: immutable.py has no third-party imports
- **WHEN** inspecting the import statements in `tlog/tlog/immutable.py`
- **THEN** only `abc` and `typing` from the standard library SHALL be imported

### Requirement: tlog contains consolidated digest computation
The `tlog` package SHALL contain a single canonical implementation of digest computation functions, eliminating the current duplication across three files.

#### Scenario: digest.py contains canonical_json
- **WHEN** inspecting `tlog/tlog/digest.py`
- **THEN** it SHALL contain a `canonical_json(data)` function that produces deterministic UTF-8 JSON serialization with sorted keys and no unnecessary whitespace

#### Scenario: digest.py contains compute_entry_digest
- **WHEN** inspecting `tlog/tlog/digest.py`
- **THEN** it SHALL contain a `compute_entry_digest(key, value)` function that returns a `sha384:`-prefixed hex digest

#### Scenario: digest.py contains compute_event_digest
- **WHEN** inspecting `tlog/tlog/digest.py`
- **THEN** it SHALL contain a `compute_event_digest(event_id, event_type, created_iso, entry_digests)` function implementing the two-level digest algorithm

#### Scenario: Digest functions produce identical results to current implementations
- **WHEN** the same inputs are passed to the consolidated digest functions
- **THEN** the outputs SHALL be byte-identical to the current implementations in `tlog_client.py`, `sigstore_baseline.py`, and `owner_attestation.py`

### Requirement: tlog __init__.py re-exports public API
The `tlog` package `__init__.py` SHALL re-export all public types, errors, ABCs, and digest functions for convenient import.

#### Scenario: Top-level imports work
- **WHEN** code imports `from tlog import Entry, ImmutableLogAdapter, compute_entry_digest`
- **THEN** the imports SHALL resolve successfully

### Requirement: tlog exposes backend extras and namespaces
The standalone `tlog` project SHALL expose backend-specific optional dependency groups and backend namespaces without requiring those backends in the base package root API.

#### Scenario: Rekor backend namespace exists
- **WHEN** inspecting the consolidated `tlog` package
- **THEN** a Rekor backend namespace SHALL exist under `tlog.backends.rekor`

#### Scenario: Base package root remains core-focused
- **WHEN** code imports from the top-level `tlog` package
- **THEN** core types, errors, ABCs, and digest helpers SHALL remain available without requiring backend modules to be imported from the top-level package root

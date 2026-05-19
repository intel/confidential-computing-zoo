## ADDED Requirements

### Requirement: Immutable-log backend adapters SHALL be independent packages
Each immutable-log backend adapter SHALL be a separate installable Python package with its own `pyproject.toml`, depending only on `tlog` plus backend-specific libraries.

#### Scenario: tlog-rekor is independently installable
- **WHEN** `pip install -e tlog-rekor/` is run in a virtual environment that has `tlog` installed
- **THEN** the installation SHALL succeed, pulling in `sigstore`, `rekor-types`, and `cryptography` as dependencies

#### Scenario: tlog-onchain is independently installable
- **WHEN** `pip install -e tlog-onchain/` is run in a virtual environment that has `tlog` installed
- **THEN** the installation SHALL succeed with its own backend-specific dependencies, without pulling `sigstore` or `rekor-types`

### Requirement: tlog-rekor contains SigstoreLogAdapter
The `tlog-rekor` package SHALL contain the Sigstore/Rekor implementation of `ImmutableLogAdapter`.

#### Scenario: SigstoreLogAdapter implements ImmutableLogAdapter
- **WHEN** inspecting `tlog-rekor/tlog_rekor/adapter.py`
- **THEN** `SigstoreLogAdapter` SHALL be defined as a concrete implementation of `tlog.immutable.ImmutableLogAdapter`

#### Scenario: SigstoreLogAdapter accepts str bundle
- **WHEN** `SigstoreLogAdapter.submit_bundle(bundle_json)` is called
- **THEN** the adapter SHALL deserialize `bundle_json` from string to `sigstore.models.Bundle` internally before submission

#### Scenario: tlog-rekor contains OciBundleMirror
- **WHEN** inspecting `tlog-rekor/tlog_rekor/oci_mirror.py`
- **THEN** `OciBundleMirror` SHALL be present, moved from `tc_api.trucon.adapters.oci_mirror`

### Requirement: tlog-onchain provides a scaffold for on-chain backend
The `tlog-onchain` package SHALL contain a placeholder `OnChainLogAdapter` class that implements `ImmutableLogAdapter` with `NotImplementedError` stubs.

#### Scenario: OnChainLogAdapter exists as a scaffold
- **WHEN** inspecting `tlog-onchain/tlog_onchain/adapter.py`
- **THEN** `OnChainLogAdapter` SHALL inherit from `tlog.immutable.ImmutableLogAdapter` and raise `NotImplementedError` for all abstract methods

### Requirement: TruCon submit daemon SHALL load backend adapters at runtime
The TruCon submit daemon SHALL select and instantiate immutable backend adapters at runtime from validated startup configuration, using direct conditional imports rather than a plugin registry. When exactly one backend is configured, TruCon SHALL load that concrete adapter directly. When more than one backend is configured, TruCon SHALL load the configured backend adapters and wrap them in a composite immutable adapter that still satisfies the `ImmutableLogAdapter` contract.

#### Scenario: Default backend configuration resolves to Rekor
- **WHEN** TruCon starts without explicit backend configuration
- **THEN** the submit daemon SHALL load `SigstoreLogAdapter` from `tlog_rekor.adapter` as the effective backend

#### Scenario: Single backend selection via environment variable
- **WHEN** the immutable backend configuration declares one supported backend such as `rekor` or `onchain`
- **THEN** the submit daemon SHALL load the corresponding adapter from the matching package

#### Scenario: Multiple backends use a composite adapter
- **WHEN** the immutable backend configuration declares more than one supported backend
- **THEN** TruCon SHALL instantiate the corresponding backend adapters and wrap them in a composite immutable adapter before passing the adapter into the submit daemon

#### Scenario: Unknown backend raises clear error
- **WHEN** the immutable backend configuration contains an unsupported backend value
- **THEN** the submit daemon SHALL raise `ValueError` with a message listing supported backends

#### Scenario: Unsupported placeholder fanout is rejected
- **WHEN** the immutable backend configuration requests `rekor,onchain` while the on-chain adapter is still a placeholder implementation
- **THEN** TruCon SHALL fail startup with a clear configuration error rather than partially enabling fanout mode

### Requirement: tc-api trucon/adapters retains only platform-specific adapters
After extraction of `SigstoreLogAdapter` and `OciBundleMirror`, the `trucon/adapters/` directory SHALL contain only platform-specific adapters that are not immutable-log backends.

#### Scenario: trucon/adapters/ contains TDX adapters
- **WHEN** inspecting `tc-api/tc_api/trucon/adapters/`
- **THEN** it SHALL contain `tdx_mr.py`, `tdx_quote.py`, and `ccel.py`

#### Scenario: sigstore.py removed from trucon/adapters
- **WHEN** inspecting `tc-api/tc_api/trucon/adapters/`
- **THEN** `sigstore.py` SHALL NOT exist (moved to `tlog-rekor`)

#### Scenario: oci_mirror.py removed from trucon/adapters
- **WHEN** inspecting `tc-api/tc_api/trucon/adapters/`
- **THEN** `oci_mirror.py` SHALL NOT exist (moved to `tlog-rekor`)

### Requirement: tc-api declares tlog and tlog-rekor as dependencies
The `tc-api` `pyproject.toml` SHALL list `tlog` and `tlog-rekor` as required dependencies.

#### Scenario: tc-api pyproject.toml has tlog dependency
- **WHEN** inspecting `tc-api/pyproject.toml`
- **THEN** `tlog` SHALL appear in the `dependencies` list

#### Scenario: tc-api pyproject.toml has tlog-rekor dependency
- **WHEN** inspecting `tc-api/pyproject.toml`
- **THEN** `tlog-rekor` SHALL appear in the `dependencies` list

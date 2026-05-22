## Purpose

Define the requirements for consolidating trusted-log backend implementations into the standalone `tlog` distribution while keeping backend dependencies opt-in and first-party imports aligned with the consolidated namespace.

## Requirements

### Requirement: tlog SHALL contain backend implementations under a dedicated namespace
The consolidated `tlog` distribution SHALL place concrete immutable-log backend implementations under a dedicated backend namespace instead of separate sibling Python projects.

#### Scenario: Rekor backend lives under tlog.backends.rekor
- **WHEN** inspecting the consolidated `tlog` package layout
- **THEN** the Rekor implementation SHALL exist under `tlog/backends/rekor/`

#### Scenario: On-chain backend scaffold lives under tlog.backends.onchain
- **WHEN** inspecting the consolidated `tlog` package layout
- **THEN** the on-chain scaffold SHALL exist under `tlog/backends/onchain/`

### Requirement: Backend dependencies SHALL remain opt-in
The consolidated `tlog` distribution SHALL expose backend-specific dependencies through optional dependency groups rather than forcing them into the base installation surface.

#### Scenario: Base tlog install remains lightweight
- **WHEN** `pip install -e tlog/` is run without backend extras
- **THEN** the installation SHALL succeed without requiring Rekor-specific third-party libraries

#### Scenario: Rekor backend dependencies are installable through extras
- **WHEN** a consumer installs the Rekor-enabled variant of `tlog`
- **THEN** the installation SHALL include the dependencies needed by the Rekor backend implementation

### Requirement: First-party backend imports SHALL use tlog.backends paths
Repository-owned code SHALL import backend adapters and mirror helpers from the consolidated `tlog.backends` namespace.

#### Scenario: TruCon imports Rekor backend from consolidated tlog
- **WHEN** `tc_api.trucon.app` loads the Rekor backend implementation
- **THEN** it SHALL import it from the consolidated `tlog.backends.rekor` namespace rather than from `tlog_rekor`

#### Scenario: On-chain backend import resolves within consolidated tlog
- **WHEN** TruCon or tests import the on-chain backend scaffold
- **THEN** they SHALL import it from the consolidated `tlog.backends.onchain` namespace rather than from `tlog_onchain`
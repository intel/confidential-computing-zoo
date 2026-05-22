## Why

The current trusted-log packaging splits one conceptual subsystem across three sibling Python projects: `tlog`, `tlog-rekor`, and `tlog-onchain`. That separation keeps dependencies isolated, but it also adds monorepo overhead, import churn, and packaging complexity disproportionate to the current implementation reality, where Rekor is the only production backend and on-chain remains a scaffold.

## What Changes

- Consolidate `tlog-rekor` and `tlog-onchain` into the `tlog` distribution under an internal backend namespace such as `tlog.backends.rekor` and `tlog.backends.onchain`.
- Preserve the logical split between shared contracts/digest logic and concrete backend implementations inside the `tlog` source tree.
- Add optional dependency groups so backend-specific dependencies remain opt-in instead of inflating the base `tlog` install surface.
- Update `tc-api` and related tooling to import backend implementations from the consolidated `tlog` package layout.
- Remove the top-level `tlog-rekor/` and `tlog-onchain/` monorepo projects once their contents have moved into `tlog/`.
- **BREAKING**: Replace public import paths such as `tlog_rekor.adapter` and `tlog_onchain.adapter` with `tlog.backends.rekor` and `tlog.backends.onchain` equivalents.

## Capabilities

### New Capabilities
- `tlog-backends-consolidation`: Consolidate backend implementations into the `tlog` distribution while preserving a backend namespace and optional dependency boundaries.

### Modified Capabilities
- `backend-adapter-isolation`: Backend adapter loading and import boundaries change from sibling backend packages to backend modules inside `tlog`.
- `tlog-package-layout`: The standalone `tlog` project layout expands from shared contracts only to a package that also contains backend implementation subpackages.
- `tlog-standalone-package`: The `tlog` package remains independently installable, but now exposes backend extras and internal backend subpackages instead of remaining strictly core-only.
- `monorepo-layout`: The repository root layout changes because `tlog-rekor/` and `tlog-onchain/` stop existing as separate top-level projects.

## Impact

- Affected code: `tlog/`, `tc-api/tc_api/trucon/app.py`, `tc-api/tc_api/trucon/submit_daemon.py`, `tc-api/tc_api/cli/verify.py`, `tc-api/tc_api/docktap/trucon_client.py`, package setup scripts, Docker/build files, and tests importing `tlog_rekor` or `tlog_onchain`.
- Affected APIs: Python import paths for backend adapters and OCI mirror helpers.
- Affected dependencies: `tlog` gains optional backend dependency groups; `tc-api` installation and local editable setup flows change accordingly.
- Affected systems: developer environment setup, container build inputs, monorepo directory conventions, and backend-related documentation/specs.
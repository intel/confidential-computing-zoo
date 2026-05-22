## Why

The current codebase is a single Python package (`tc_api`) that will be merged into a multi-project monorepo (`agent-cc/core/`). The shared trust-log abstractions (types, ABCs, digest computation) are locked inside `tc_api`, making them unavailable to sibling projects (`argus`, `tdx-skills`) and upper-layer integrations without pulling in the entire `tc_api` dependency tree. Additionally, the Sigstore/Rekor backend adapter lives inside `trucon/`, forcing any consumer (including the standalone verifier CLI) to depend on TruCon sequencer internals. As on-chain immutable backends are planned, mixing heavy Sigstore dependencies with future Web3 dependencies in one package is unsustainable. Extracting `tlog` as an independent package and isolating backend adapters into separate packages resolves these dependency-direction and isolation problems before the monorepo merge.

## What Changes

- **Extract `tlog` as an independent Python package** — Move `src/tc_api/tlog/` (types, ABCs, errors) plus digest computation and evidence encoding into a standalone `tlog/` project with its own `pyproject.toml`. This package becomes the shared contract layer across all `agent-cc/core/` projects.
- **Extract `tlog-rekor` as an independent backend package** — Move `SigstoreLogAdapter`, `OciBundleMirror`, and intoto helpers out of `trucon/adapters/` into a standalone `tlog-rekor/` project. This package depends only on `tlog` plus Sigstore/Rekor libraries.
- **Scaffold `tlog-onchain` backend package** — Create a placeholder `tlog-onchain/` project for the planned on-chain `ImmutableLogAdapter` implementation, depending only on `tlog`.
- **Update `tc-api` to depend on `tlog` and `tlog-rekor`** — Rewrite import paths throughout `tc_api`, `trucon`, `docktap`, and `cli` to use the extracted packages. `trucon/adapters/` retains only non-log adapters (`tdx_mr`, `tdx_quote`, `ccel`).
- **BREAKING**: All import paths for `tlog` types change from `tc_api.tlog.*` to `tlog.*`.
- **BREAKING**: `SigstoreLogAdapter` import path changes from `tc_api.trucon.adapters.sigstore` to `tlog_rekor.adapter`.
- **Update `pyproject.toml`** — `tc-api` adds `tlog` and `tlog-rekor` as dependencies; `tlog` has minimal dependencies; `tlog-rekor` depends on `tlog`, `sigstore`, `rekor-types`.

## Capabilities

### New Capabilities
- `tlog-standalone-package`: Requirements for `tlog` as an independent installable package with its own `pyproject.toml`, containing shared types, ABCs (`ImmutableLogAdapter`, `LocalMRAdapter`), digest computation, errors, and evidence encoding — with zero dependency on `tc_api`.
- `backend-adapter-isolation`: Requirements for extracting immutable-log backend adapters (`tlog-rekor`, future `tlog-onchain`) into independent packages that depend only on `tlog` plus backend-specific libraries, loadable at runtime by TruCon's submit daemon.
- `import-path-migration`: Requirements for updating all import paths across `tc_api`, `trucon`, `docktap`, `cli`, and tests to reference the extracted `tlog` and `tlog-rekor` packages instead of `tc_api.tlog.*` and `tc_api.trucon.adapters.sigstore`.

### Modified Capabilities
- `tlog-package-layout`: The three-layer structure (tlog/shared, trucon/internals, tlog_client) changes — `tlog` becomes a separate installable package rather than a sub-package of `tc_api`. Import path conventions defined in this spec must be updated.

## Impact

- **Code**: Every file importing from `tc_api.tlog.*` or `tc_api.trucon.adapters.sigstore` needs import path updates. Key files: `main.py`, `services.py`, `tlog_client.py`, `trucon/app.py`, `trucon/adapters/sigstore.py` (moves entirely), `cli/verify.py`, `docktap/trucon_client.py`.
- **Build**: Three new `pyproject.toml` files (`tlog/`, `tlog-rekor/`, `tlog-onchain/`). Root `pyproject.toml` gains workspace/dependency references.
- **Dependencies**: `sigstore`, `rekor-types`, `cryptography` move from `tc-api` to `tlog-rekor`. `tc-api` gains transitive access via `tlog-rekor` dependency.
- **Deployment**: `Dockerfile`, `docker-compose.yml`, `start.sh` need path adjustments for the new project layout.
- **Tests**: Test files importing from `tc_api.tlog.*` and `tc_api.trucon.adapters.sigstore` need import updates. Test fixtures and mocks for `ImmutableLogAdapter` may need adjustment.
- **Existing specs**: `tlog-package-layout` spec needs revision to reflect cross-package boundaries instead of intra-package layers.

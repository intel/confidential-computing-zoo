## 1. Consolidate Package Structure

- [x] 1.1 Move the Rekor adapter and OCI mirror modules from `tlog-rekor/` into a backend namespace under `tlog/`.
- [x] 1.2 Move the on-chain scaffold from `tlog-onchain/` into a backend namespace under `tlog/` while preserving its placeholder behavior.
- [x] 1.3 Update `tlog/pyproject.toml` to expose backend extras and package discovery for the consolidated backend subpackages.

## 2. Migrate First-Party Imports

- [x] 2.1 Replace first-party imports of `tlog_rekor.*` with `tlog.backends.rekor.*` across `tc-api`, scripts, and tests.
- [x] 2.2 Replace first-party imports of `tlog_onchain.*` with `tlog.backends.onchain.*` where the scaffold is referenced.
- [x] 2.3 Update TruCon backend-loading code and related tests to resolve backend implementations from the consolidated `tlog.backends` namespace.

## 3. Simplify Build and Setup Flows

- [x] 3.1 Update `tc-api` setup helpers, editable-install instructions, and package metadata to reference the consolidated `tlog` project instead of sibling backend projects.
- [x] 3.2 Update Docker and build inputs so container/image assembly copies only the consolidated `tlog/` project rather than separate `tlog-rekor/` and `tlog-onchain/` directories.
- [x] 3.3 Remove the top-level `tlog-rekor/` and `tlog-onchain/` project directories after their contents and references have been migrated.

## 4. Validate Consolidated Layout

- [x] 4.1 Add or update tests that verify backend imports, package metadata, and TruCon runtime loading work from the consolidated `tlog.backends` namespace.
- [x] 4.2 Run the focused trusted-log, TruCon, and packaging test slices needed to validate the import-path and setup migration.
- [x] 4.3 Update developer-facing documentation to describe the consolidated `tlog` layout, backend extras, and new import paths.
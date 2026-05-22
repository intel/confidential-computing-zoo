## Why

The product identity has been updated to docktap in documentation, but the repository still uses the legacy folder name sock-bridge. This mismatch causes confusion for contributors and operators and leaves commands/examples inconsistent with the new canonical name.

## What Changes

- Rename the top-level folder from sock-bridge to docktap.
- Update all repository references to the folder path in docs, tests, scripts, and OpenSpec artifacts.
- Provide compatibility handling or migration notes for commands that still reference sock-bridge.
- **BREAKING**: direct path references and tooling that depend on sock-bridge paths will need to switch to docktap.

## Capabilities

### New Capabilities
- `docktap-folder-rename`: Ensure the runtime/test workspace is migrated from sock-bridge pathing to docktap pathing with validated reference updates.

### Modified Capabilities
- None.

## Impact

- Affected areas:
  - filesystem layout (`sock-bridge/` -> `docktap/`)
  - path references in markdown, Python test scripts, and OpenSpec change artifacts
  - command examples and automation that run from the old folder path
- Potential downstream impact:
  - developer scripts or CI jobs with hardcoded sock-bridge paths must be updated
- Validation needed:
  - search-based path reference audit
  - targeted and full test execution using new docktap path

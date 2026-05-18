## Why

The current project name `sock-bridge` no longer communicates the primary product identity and trust-observability purpose. Renaming to `docktap` improves clarity for users, operators, and documentation consumers while keeping the same functional scope.

## What Changes

- Rename the product identity from `sock-bridge` to `docktap` across repository documentation and OpenSpec artifacts.
- Align user-facing naming in architecture, README, and change documents to use `docktap` consistently.
- Define migration-safe handling for legacy references where immediate hard rename is not possible.
- Add verification steps to ensure no stale `sock-bridge` references remain in targeted documentation scopes.

## Capabilities

### New Capabilities
- `docktap-identity-rename`: Define and enforce consistent `docktap` naming across product documentation and OpenSpec change artifacts.

### Modified Capabilities
- None.

## Impact

- Affected docs and artifacts:
  - markdown files under `docktap/`
  - markdown files under `openspec/` relevant to product naming
- Potentially affected scripts/tests if naming strings are asserted in outputs.
- No runtime behavior change intended from this rename change alone.

## 1. Inventory and Rename Preparation

- [x] 1.1 Enumerate all references to `sock-bridge/` across docs, tests, scripts, and OpenSpec artifacts.
- [x] 1.2 Categorize references into required path migrations vs intentional historical mentions.
- [x] 1.3 Prepare a migration checklist that includes folder move order and verification commands.

## 2. Folder and Path Migration

- [x] 2.1 Rename repository folder `sock-bridge/` to `docktap/`.
- [x] 2.2 Update repository path references from `sock-bridge/...` to `docktap/...` where they represent active usage.
- [x] 2.3 Update command examples and working-directory instructions to use `docktap` paths.

## 3. OpenSpec and Documentation Alignment

- [x] 3.1 Update active OpenSpec artifacts that reference operational folder paths to use `docktap/...`.
- [x] 3.2 Preserve and document intentional historical references where changing names would break change identity/history.
- [x] 3.3 Ensure architecture/README wording remains clear after path migration.

## 4. Validation and Rollout Readiness

- [x] 4.1 Re-run scoped search checks to identify any stale `sock-bridge/` path references.
- [x] 4.2 Run rename-impacted tests/commands from the new folder location.
- [x] 4.3 Document final migration results, residual exceptions, and recommended follow-up actions.

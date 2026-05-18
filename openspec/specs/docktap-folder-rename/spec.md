# docktap-folder-rename Specification

## Purpose
TBD - created by archiving change rename-sock-bridge-folder-to-docktap. Update Purpose after archive.
## Requirements
### Requirement: Folder Rename Completeness
The repository SHALL rename the folder `sock-bridge/` to `docktap/` as part of this change.

#### Scenario: Repository layout reflects new folder name
- **WHEN** the change is applied
- **THEN** a `docktap/` directory exists with migrated contents and `sock-bridge/` no longer remains as the primary working folder

### Requirement: Path Reference Consistency
In-repository references SHALL be updated so operational commands and documentation point to `docktap/` paths after the rename.

#### Scenario: Docs and scripts use docktap path
- **WHEN** markdown files and maintained scripts are reviewed after rename
- **THEN** path references for active usage point to `docktap/...` instead of `sock-bridge/...`

### Requirement: Migration Validation
The folder rename SHALL include validation that detects missed path references and verifies expected test execution from the new location.

#### Scenario: Validation catches stale references
- **WHEN** post-rename audits are run
- **THEN** remaining `sock-bridge` path matches are either fixed or documented as intentional historical exceptions

#### Scenario: Test suite runs from new folder
- **WHEN** canonical test commands are executed from the renamed folder context
- **THEN** core rename-impacted tests complete successfully


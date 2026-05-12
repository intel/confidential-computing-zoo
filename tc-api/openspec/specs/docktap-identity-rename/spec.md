# docktap-identity-rename Specification

## Purpose
TBD - created by archiving change rename-sock-bridge-to-docktap. Update Purpose after archive.
## Requirements
### Requirement: Canonical Product Naming
Documentation in targeted rename scope SHALL use `docktap` as the canonical product identity in place of `sock-bridge`.

#### Scenario: Identity text is updated in scope
- **WHEN** markdown documents under the approved rename scope are reviewed
- **THEN** product identity wording uses `docktap` consistently for user-facing references

### Requirement: Safe Rename Boundaries
The rename process SHALL preserve technical literals that must remain unchanged for correctness (for example existing filesystem paths, historical identifiers, or quoted outputs) unless explicitly included in rename scope.

#### Scenario: Literal path references remain accurate
- **WHEN** documentation contains executable path literals that still use existing directory names
- **THEN** those literals are preserved or intentionally migrated with corresponding filesystem changes

### Requirement: Verification of Residual References
The change SHALL include verification that no unintended `sock-bridge` identity references remain in targeted documentation.

#### Scenario: Residual references are audited
- **WHEN** the rename pass is complete
- **THEN** search-based validation is performed and remaining matches are reviewed with justification


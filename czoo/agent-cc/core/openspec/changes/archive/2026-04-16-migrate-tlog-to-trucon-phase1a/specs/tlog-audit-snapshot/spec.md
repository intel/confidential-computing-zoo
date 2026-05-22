## ADDED Requirements

### Requirement: Commit receipt saved after commit_record
After `commit_record()` returns a `CommitResult`, the system SHALL save a JSON receipt file to `builds/<id>/<type>-commit-receipt.json` containing the `record_id`, `event_id`, `queue_status`, and `mr_value` fields from the result.

#### Scenario: Build commit receipt saved
- **WHEN** the build workflow calls `commit_record()` and receives a `CommitResult`
- **THEN** a file `builds/<build_id>/build-commit-receipt.json` SHALL be created with the commit metadata

#### Scenario: Publish commit receipt saved
- **WHEN** the publish workflow calls `commit_record()` and receives a `CommitResult`
- **THEN** a file `builds/<build_id>/publish-commit-receipt.json` SHALL be created with the commit metadata

#### Scenario: Launch commit receipt saved
- **WHEN** the launch workflow calls `commit_record()` and receives a `CommitResult`
- **THEN** a file `builds/<launch_id>/launch-commit-receipt.json` SHALL be created with the commit metadata

### Requirement: Legacy transparency files no longer produced
The system SHALL NOT produce the legacy `<type>-transparency.json`, `<type>-transparency_log-<idx>.sigstore.json`, or `<type>-chain.sigstore.json` files. The commit receipt replaces all three.

#### Scenario: No legacy chain file after build
- **WHEN** a build workflow completes
- **THEN** no `build-chain.sigstore.json` file SHALL be created in the build directory

### Requirement: Lightweight verification via TruCon chain-state query
The `verify_transpaerncyLog` method SHALL be replaced by a function that queries TruCon `GET /chain-state/{chain_id}` and checks that the chain head record matches the expected record_id from the commit receipt.

#### Scenario: Verification confirms sequenced commit
- **WHEN** verification is called with a chain_id and expected record_id
- **THEN** it SHALL query TruCon chain-state and confirm the head_record_id matches or the sequence_num is at least as high as expected

#### Scenario: TruCon unreachable during verification
- **WHEN** TruCon is not reachable during verification
- **THEN** the system SHALL log a warning and return a degraded verification status instead of failing the workflow
